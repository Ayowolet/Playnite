using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using Playnite.SDK;

namespace Playnite.PythonBridge
{
    /// <summary>
    /// Manages the lifecycle of the Python service process.
    /// </summary>
    public class PythonServiceManager
    {
        private readonly ILogger logger;
        private readonly PythonServiceClient serviceClient;
        private Process serviceProcess;
        private readonly string pythonExecutable = "python";
        private readonly string servicePath;

        public PythonServiceManager(ILogger logger, PythonServiceClient serviceClient)
        {
            this.logger = logger;
            this.serviceClient = serviceClient;

            // Determine service path (relative to plugin directory)
            var pluginDir = Path.GetDirectoryName(typeof(PythonServiceManager).Assembly.Location);
            this.servicePath = Path.Combine(pluginDir, "..", "..", "playnite-python");
        }

        /// <summary>
        /// Ensure the Python service is running, starting it if necessary.
        /// </summary>
        public async Task<bool> EnsureServiceRunningAsync()
        {
            // Check if service is already running
            if (await serviceClient.CheckHealthAsync())
            {
                logger.Info("Python service is already running");
                return true;
            }

            logger.Info("Python service not running, attempting to start...");

            // Try to start the service
            return await StartServiceAsync();
        }

        /// <summary>
        /// Start the Python service process.
        /// </summary>
        private async Task<bool> StartServiceAsync()
        {
            try
            {
                // Check if Python is available
                if (!IsPythonAvailable())
                {
                    logger.Error("Python executable not found. Please ensure Python 3.8+ is installed.");
                    return false;
                }

                // Check if service directory exists
                if (!Directory.Exists(servicePath))
                {
                    logger.Error($"Python service directory not found: {servicePath}");
                    return false;
                }

                // Start the Python service
                var startInfo = new ProcessStartInfo
                {
                    FileName = pythonExecutable,
                    Arguments = "-m playnite_python serve",
                    WorkingDirectory = servicePath,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };

                serviceProcess = Process.Start(startInfo);

                if (serviceProcess == null)
                {
                    logger.Error("Failed to start Python service process");
                    return false;
                }

                logger.Info($"Started Python service (PID: {serviceProcess.Id})");

                // Wait for service to become healthy (max 30 seconds)
                for (int i = 0; i < 30; i++)
                {
                    await Task.Delay(1000);

                    if (await serviceClient.CheckHealthAsync())
                    {
                        logger.Info("Python service is healthy and ready");
                        return true;
                    }
                }

                logger.Error("Python service failed to become healthy within 30 seconds");
                return false;
            }
            catch (Exception ex)
            {
                logger.Error(ex, "Failed to start Python service");
                return false;
            }
        }

        /// <summary>
        /// Stop the Python service if it was started by this manager.
        /// </summary>
        public void StopService()
        {
            if (serviceProcess != null && !serviceProcess.HasExited)
            {
                try
                {
                    logger.Info("Stopping Python service...");
                    serviceProcess.Kill();
                    serviceProcess.WaitForExit(5000);
                    logger.Info("Python service stopped");
                }
                catch (Exception ex)
                {
                    logger.Error(ex, "Failed to stop Python service");
                }
            }
        }

        /// <summary>
        /// Check if Python is available in PATH.
        /// </summary>
        private bool IsPythonAvailable()
        {
            try
            {
                var process = Process.Start(new ProcessStartInfo
                {
                    FileName = pythonExecutable,
                    Arguments = "--version",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true
                });

                process?.WaitForExit();
                return process?.ExitCode == 0;
            }
            catch
            {
                return false;
            }
        }
    }
}
