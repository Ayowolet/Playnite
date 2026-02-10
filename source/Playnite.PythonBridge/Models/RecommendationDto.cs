using System;
using System.Collections.Generic;

namespace Playnite.PythonBridge.Models
{
    /// <summary>
    /// Simplified game data for sending to Python service.
    /// </summary>
    public class GameDto
    {
        public string GameId { get; set; }
        public string Name { get; set; }
        public List<string> Genres { get; set; }
        public List<string> Developers { get; set; }
        public List<string> Publishers { get; set; }
        public List<string> Platforms { get; set; }
        public List<string> Tags { get; set; }
        public List<string> Features { get; set; }
        public int PlaytimeSeconds { get; set; }
        public int PlayCount { get; set; }
        public DateTime? LastActivity { get; set; }
        public int? UserScore { get; set; }
        public int? CommunityScore { get; set; }
        public int? CriticScore { get; set; }
        public string CompletionStatus { get; set; }
        public bool IsInstalled { get; set; }
        public bool Favorite { get; set; }
        public bool Hidden { get; set; }
    }

    /// <summary>
    /// Request for generating recommendations.
    /// </summary>
    public class RecommendationRequest
    {
        public string UserId { get; set; }
        public List<GameDto> Library { get; set; }
        public RecommendationContext Context { get; set; }
        public int Limit { get; set; } = 10;
    }

    /// <summary>
    /// Context for recommendation generation.
    /// </summary>
    public class RecommendationContext
    {
        public string Mood { get; set; }
        public string TimeOfDay { get; set; }
        public string SessionLength { get; set; }
    }

    /// <summary>
    /// Individual recommendation response.
    /// </summary>
    public class RecommendationResponse
    {
        public string GameId { get; set; }
        public string GameName { get; set; }
        public double Score { get; set; }
        public string Reason { get; set; }
        public Dictionary<string, object> Factors { get; set; }
        public List<string> Sources { get; set; }
    }

    /// <summary>
    /// List of recommendations with metadata.
    /// </summary>
    public class RecommendationListResponse
    {
        public List<RecommendationResponse> Recommendations { get; set; }
        public int Count { get; set; }
        public string GeneratedAt { get; set; }
        public string ModelVersion { get; set; }
    }
}
