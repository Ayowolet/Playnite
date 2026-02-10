namespace Playnite.PythonBridge.Models
{
    /// <summary>
    /// Capture settings for a session.
    /// </summary>
    public class CaptureSettings
    {
        public string ScreenshotHotkey { get; set; } = "f8";
        public string VideoHotkey { get; set; } = "f9";
        public string Backend { get; set; } = "direct";
        public string VideoQuality { get; set; } = "high";
    }

    /// <summary>
    /// Request to start a capture session.
    /// </summary>
    public class StartCaptureRequest
    {
        public string GameId { get; set; }
        public string GameName { get; set; }
        public int ProcessId { get; set; }
        public CaptureSettings Settings { get; set; }
    }

    /// <summary>
    /// Response from starting a capture session.
    /// </summary>
    public class CaptureSessionResponse
    {
        public string SessionId { get; set; }
        public string Status { get; set; }
        public string GameName { get; set; }
        public string Backend { get; set; }
        public int ScreenshotCount { get; set; }
        public int VideoCount { get; set; }
    }
}
