using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Playnite.SDK;
using Playnite.SDK.Models;
using Playnite.PythonBridge.Models;

namespace Playnite.PythonBridge.Services
{
    /// <summary>
    /// Exports game library data from Playnite for use by Python service.
    /// </summary>
    public class GameDataExporter
    {
        private readonly IPlayniteAPI playniteApi;
        private readonly ILogger logger;

        public GameDataExporter(IPlayniteAPI playniteApi, ILogger logger)
        {
            this.playniteApi = playniteApi;
            this.logger = logger;
        }

        /// <summary>
        /// Export entire game library to GameDto list.
        /// </summary>
        public List<GameDto> ExportLibrary()
        {
            var games = playniteApi.Database.Games
                .Select(game => ConvertToDto(game))
                .ToList();

            logger.Info($"Exported {games.Count} games from library");
            return games;
        }

        /// <summary>
        /// Export library to JSON file for testing/debugging.
        /// </summary>
        public void ExportToJsonFile(string filePath)
        {
            try
            {
                var library = ExportLibrary();
                var json = JsonConvert.SerializeObject(library, Formatting.Indented);
                File.WriteAllText(filePath, json);
                logger.Info($"Exported library to: {filePath}");
            }
            catch (Exception ex)
            {
                logger.Error(ex, $"Failed to export library to JSON: {filePath}");
                throw;
            }
        }

        /// <summary>
        /// Convert a Playnite Game object to GameDto.
        /// </summary>
        private GameDto ConvertToDto(Game game)
        {
            return new GameDto
            {
                GameId = game.Id.ToString(),
                Name = game.Name,
                Genres = game.Genres?.Select(g => g.Name).ToList() ?? new List<string>(),
                Developers = game.Developers?.Select(d => d.Name).ToList() ?? new List<string>(),
                Publishers = game.Publishers?.Select(p => p.Name).ToList() ?? new List<string>(),
                Platforms = game.Platforms?.Select(p => p.Name).ToList() ?? new List<string>(),
                Tags = game.Tags?.Select(t => t.Name).ToList() ?? new List<string>(),
                Features = game.Features?.Select(f => f.Name).ToList() ?? new List<string>(),
                PlaytimeSeconds = (int)game.Playtime,
                PlayCount = (int)game.PlayCount,
                LastActivity = game.LastActivity,
                UserScore = game.UserScore,
                CommunityScore = game.CommunityScore,
                CriticScore = game.CriticScore,
                CompletionStatus = game.CompletionStatus?.Name,
                IsInstalled = game.IsInstalled,
                Favorite = game.Favorite,
                Hidden = game.Hidden
            };
        }
    }
}
