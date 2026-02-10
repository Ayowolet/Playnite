using System;

namespace Playnite.PythonBridge.Models
{
    /// <summary>
    /// Data transfer object for game start events.
    /// </summary>
    public class GameEventDto
    {
        public string GameId { get; set; }
        public string GameName { get; set; }
        public int ProcessId { get; set; }
        public string UserId { get; set; }
        public DateTime Timestamp { get; set; }
    }

    /// <summary>
    /// Data transfer object for game stop events.
    /// </summary>
    public class GameStoppedEventDto
    {
        public string GameId { get; set; }
        public ulong ElapsedSeconds { get; set; }
        public DateTime Timestamp { get; set; }
    }
}
