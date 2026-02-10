using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Playnite.SDK;
using Playnite.PythonBridge.Models;

namespace Playnite.PythonBridge
{
    /// <summary>
    /// Client for communicating with the Python service via HTTP REST API.
    /// </summary>
    public class PythonServiceClient
    {
        private readonly HttpClient httpClient;
        private readonly string baseUrl;
        private readonly ILogger logger;

        public PythonServiceClient(string baseUrl, ILogger logger)
        {
            this.baseUrl = baseUrl;
            this.logger = logger;
            this.httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromSeconds(30)
            };
        }

        /// <summary>
        /// Check if the Python service is healthy and responding.
        /// </summary>
        public async Task<bool> CheckHealthAsync()
        {
            try
            {
                var response = await httpClient.GetAsync($"{baseUrl}/api/v1/health");
                return response.IsSuccessStatusCode;
            }
            catch (Exception ex)
            {
                logger.Debug($"Health check failed: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Notify the Python service that a game has started.
        /// </summary>
        public async Task NotifyGameStartedAsync(GameEventDto gameEvent)
        {
            try
            {
                await PostAsync("/api/v1/events/game-started", gameEvent);
                logger.Info($"Notified Python service: game started - {gameEvent.GameName}");
            }
            catch (Exception ex)
            {
                logger.Error(ex, $"Failed to notify game started: {gameEvent.GameName}");
            }
        }

        /// <summary>
        /// Notify the Python service that a game has stopped.
        /// </summary>
        public async Task NotifyGameStoppedAsync(GameStoppedEventDto gameEvent)
        {
            try
            {
                await PostAsync("/api/v1/events/game-stopped", gameEvent);
                logger.Info($"Notified Python service: game stopped - {gameEvent.GameId}");
            }
            catch (Exception ex)
            {
                logger.Error(ex, $"Failed to notify game stopped: {gameEvent.GameId}");
            }
        }

        /// <summary>
        /// Get game recommendations from the Python service.
        /// </summary>
        public async Task<RecommendationListResponse> GetRecommendationsAsync(RecommendationRequest request)
        {
            try
            {
                var response = await PostAsync<RecommendationListResponse>(
                    "/api/v1/recommendations/generate",
                    request
                );
                logger.Info($"Received {response.Count} recommendations from Python service");
                return response;
            }
            catch (Exception ex)
            {
                logger.Error(ex, "Failed to get recommendations from Python service");
                throw;
            }
        }

        /// <summary>
        /// Start a capture session for a game.
        /// </summary>
        public async Task<CaptureSessionResponse> StartCaptureSessionAsync(StartCaptureRequest request)
        {
            try
            {
                var response = await PostAsync<CaptureSessionResponse>(
                    "/api/v1/capture/start",
                    request
                );
                logger.Info($"Started capture session: {response.SessionId}");
                return response;
            }
            catch (Exception ex)
            {
                logger.Error(ex, $"Failed to start capture session for {request.GameName}");
                throw;
            }
        }

        /// <summary>
        /// Stop a capture session.
        /// </summary>
        public async Task StopCaptureSessionAsync(string sessionId)
        {
            try
            {
                await PostAsync($"/api/v1/capture/stop/{sessionId}", null);
                logger.Info($"Stopped capture session: {sessionId}");
            }
            catch (Exception ex)
            {
                logger.Error(ex, $"Failed to stop capture session: {sessionId}");
            }
        }

        // Helper methods for HTTP communication

        private async Task PostAsync(string endpoint, object data)
        {
            var json = JsonConvert.SerializeObject(data);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var response = await httpClient.PostAsync($"{baseUrl}{endpoint}", content);
            response.EnsureSuccessStatusCode();
        }

        private async Task<T> PostAsync<T>(string endpoint, object data)
        {
            var json = JsonConvert.SerializeObject(data);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var response = await httpClient.PostAsync($"{baseUrl}{endpoint}", content);
            response.EnsureSuccessStatusCode();

            var responseJson = await response.Content.ReadAsStringAsync();
            return JsonConvert.DeserializeObject<T>(responseJson);
        }
    }
}
