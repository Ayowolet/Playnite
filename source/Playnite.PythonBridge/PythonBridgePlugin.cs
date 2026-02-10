using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Controls;
using Playnite.SDK;
using Playnite.SDK.Events;
using Playnite.SDK.Models;
using Playnite.SDK.Plugins;
using Playnite.PythonBridge.Models;
using Playnite.PythonBridge.Services;

namespace Playnite.PythonBridge
{
    public class PythonBridgePlugin : GenericPlugin
    {
        private readonly ILogger logger;
        private readonly PythonServiceClient serviceClient;
        private readonly PythonServiceManager serviceManager;
        private readonly GameDataExporter gameDataExporter;

        // Track active capture sessions
        private readonly Dictionary<Guid, string> activeCaptureSessionsByGameId = new Dictionary<Guid, string>();

        public override Guid Id { get; } = Guid.Parse("12345678-1234-1234-1234-123456789012");

        public PythonBridgePlugin(IPlayniteAPI api) : base(api)
        {
            logger = LogManager.GetLogger();
            serviceClient = new PythonServiceClient("http://localhost:5555", logger);
            serviceManager = new PythonServiceManager(logger, serviceClient);
            gameDataExporter = new GameDataExporter(api, logger);

            logger.Info("Python Bridge Plugin initialized");
        }

        public override IEnumerable<MainMenuItem> GetMainMenuItems(GetMainMenuItemsArgs args)
        {
            return new List<MainMenuItem>
            {
                new MainMenuItem
                {
                    Description = "What Should I Play?",
                    MenuSection = "@Python Features|Recommendations",
                    Action = async (_) => await ShowRecommendationsAsync()
                },
                new MainMenuItem
                {
                    Description = "Export Library to JSON",
                    MenuSection = "@Python Features|Tools",
                    Action = (_) => ExportLibraryToJson()
                },
                new MainMenuItem
                {
                    Description = "View Capture Storage",
                    MenuSection = "@Python Features|Captures",
                    Action = (_) => OpenCaptureStorage()
                },
                new MainMenuItem
                {
                    Description = "Check Python Service Status",
                    MenuSection = "@Python Features|Tools",
                    Action = async (_) => await CheckServiceStatusAsync()
                }
            };
        }

        public override void OnApplicationStarted(OnApplicationStartedEventArgs args)
        {
            logger.Info("Playnite started, ensuring Python service is running...");

            // Start Python service in background
            Task.Run(async () =>
            {
                var success = await serviceManager.EnsureServiceRunningAsync();
                if (success)
                {
                    PlayniteApi.Notifications.Add(
                        "python-service-ready",
                        "Python features are ready! Check the menu for recommendations and capture.",
                        NotificationType.Info
                    );
                }
                else
                {
                    PlayniteApi.Notifications.Add(
                        "python-service-failed",
                        "Failed to start Python service. Recommendations and capture features will not be available.",
                        NotificationType.Error
                    );
                }
            });
        }

        public override void OnApplicationStopped(OnApplicationStoppedEventArgs args)
        {
            logger.Info("Playnite stopping, cleaning up Python service...");
            serviceManager.StopService();
        }

        public override void OnGameStarted(OnGameStartedEventArgs args)
        {
            logger.Info($"Game started: {args.Game.Name}");

            Task.Run(async () =>
            {
                // Notify Python service
                await serviceClient.NotifyGameStartedAsync(new GameEventDto
                {
                    GameId = args.Game.Id.ToString(),
                    GameName = args.Game.Name,
                    ProcessId = args.StartedProcessId,
                    UserId = "default-user",
                    Timestamp = DateTime.UtcNow
                });

                // Start capture session
                try
                {
                    var captureRequest = new StartCaptureRequest
                    {
                        GameId = args.Game.Id.ToString(),
                        GameName = args.Game.Name,
                        ProcessId = args.StartedProcessId,
                        Settings = new CaptureSettings
                        {
                            ScreenshotHotkey = "f8",
                            VideoHotkey = "f9",
                            Backend = "direct",
                            VideoQuality = "high"
                        }
                    };

                    var captureSession = await serviceClient.StartCaptureSessionAsync(captureRequest);
                    activeCaptureSessionsByGameId[args.Game.Id] = captureSession.SessionId;

                    logger.Info($"Capture session started for {args.Game.Name}: {captureSession.SessionId}");
                }
                catch (Exception ex)
                {
                    logger.Error(ex, $"Failed to start capture session for {args.Game.Name}");
                }
            });
        }

        public override void OnGameStopped(OnGameStoppedEventArgs args)
        {
            logger.Info($"Game stopped: {args.Game.Name} (played {args.ElapsedSeconds} seconds)");

            Task.Run(async () =>
            {
                // Notify Python service
                await serviceClient.NotifyGameStoppedAsync(new GameStoppedEventDto
                {
                    GameId = args.Game.Id.ToString(),
                    ElapsedSeconds = args.ElapsedSeconds,
                    Timestamp = DateTime.UtcNow
                });

                // Stop capture session
                if (activeCaptureSessionsByGameId.TryGetValue(args.Game.Id, out string sessionId))
                {
                    try
                    {
                        await serviceClient.StopCaptureSessionAsync(sessionId);
                        activeCaptureSessionsByGameId.Remove(args.Game.Id);
                        logger.Info($"Capture session stopped for {args.Game.Name}");
                    }
                    catch (Exception ex)
                    {
                        logger.Error(ex, $"Failed to stop capture session for {args.Game.Name}");
                    }
                }
            });
        }

        // Menu item implementations

        private async Task ShowRecommendationsAsync()
        {
            try
            {
                PlayniteApi.Dialogs.ActivateGlobalProgress(
                    progress =>
                    {
                        progress.ProgressMaxValue = 100;
                        progress.CurrentProgressValue = 10;
                        progress.Text = "Analyzing your game library...";
                    },
                    new GlobalProgressOptions("Generating Recommendations", true)
                );

                // Export library
                var library = gameDataExporter.ExportLibrary();

                // Request recommendations
                var request = new RecommendationRequest
                {
                    UserId = "default-user",
                    Library = library,
                    Limit = 10
                };

                var recommendations = await serviceClient.GetRecommendationsAsync(request);

                PlayniteApi.Dialogs.DeactivateGlobalProgress();

                // Display recommendations
                if (recommendations.Recommendations.Count == 0)
                {
                    PlayniteApi.Dialogs.ShowMessage(
                        "No recommendations found. Try playing more games to build your preference profile!",
                        "No Recommendations"
                    );
                    return;
                }

                // Build message
                var message = "Based on your play history, we recommend:\n\n";
                foreach (var rec in recommendations.Recommendations.Take(5))
                {
                    var game = PlayniteApi.Database.Games.FirstOrDefault(g => g.Id.ToString() == rec.GameId);
                    var gameName = game?.Name ?? rec.GameName ?? "Unknown Game";
                    message += $"• {gameName}\n  {rec.Reason} (Score: {rec.Score:F2})\n\n";
                }

                PlayniteApi.Dialogs.ShowMessage(message, "What Should You Play?");
            }
            catch (Exception ex)
            {
                PlayniteApi.Dialogs.DeactivateGlobalProgress();
                logger.Error(ex, "Failed to get recommendations");
                PlayniteApi.Dialogs.ShowErrorMessage(
                    $"Failed to get recommendations: {ex.Message}\n\nEnsure the Python service is running.",
                    "Recommendation Error"
                );
            }
        }

        private void ExportLibraryToJson()
        {
            try
            {
                var savePath = PlayniteApi.Dialogs.SaveFile("JSON|*.json");
                if (string.IsNullOrEmpty(savePath))
                    return;

                gameDataExporter.ExportToJsonFile(savePath);

                PlayniteApi.Dialogs.ShowMessage(
                    $"Library exported successfully to:\n{savePath}\n\nYou can use this file with the Python CLI for testing.",
                    "Export Successful"
                );
            }
            catch (Exception ex)
            {
                logger.Error(ex, "Failed to export library");
                PlayniteApi.Dialogs.ShowErrorMessage($"Failed to export library: {ex.Message}", "Export Error");
            }
        }

        private void OpenCaptureStorage()
        {
            try
            {
                var capturePath = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                    "Playnite",
                    "Captures"
                );

                if (System.IO.Directory.Exists(capturePath))
                {
                    System.Diagnostics.Process.Start("explorer.exe", capturePath);
                }
                else
                {
                    PlayniteApi.Dialogs.ShowMessage(
                        "No captures found yet. Play a game and press F8 to take screenshots!",
                        "No Captures"
                    );
                }
            }
            catch (Exception ex)
            {
                logger.Error(ex, "Failed to open capture storage");
                PlayniteApi.Dialogs.ShowErrorMessage($"Failed to open capture storage: {ex.Message}", "Error");
            }
        }

        private async Task CheckServiceStatusAsync()
        {
            var healthy = await serviceClient.CheckHealthAsync();

            if (healthy)
            {
                PlayniteApi.Dialogs.ShowMessage(
                    "Python service is running and healthy!\n\nEndpoint: http://localhost:5555\nAPI Docs: http://localhost:5555/docs",
                    "Service Status"
                );
            }
            else
            {
                var result = PlayniteApi.Dialogs.ShowMessage(
                    "Python service is not responding.\n\nWould you like to try starting it?",
                    "Service Status",
                    System.Windows.MessageBoxButton.YesNo
                );

                if (result == System.Windows.MessageBoxResult.Yes)
                {
                    var success = await serviceManager.EnsureServiceRunningAsync();
                    if (success)
                    {
                        PlayniteApi.Dialogs.ShowMessage("Python service started successfully!", "Success");
                    }
                    else
                    {
                        PlayniteApi.Dialogs.ShowErrorMessage(
                            "Failed to start Python service. Check logs for details.",
                            "Service Start Failed"
                        );
                    }
                }
            }
        }
    }
}
