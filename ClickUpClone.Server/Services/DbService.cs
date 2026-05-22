using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using ClickUpClone.Shared.Models;
using Microsoft.Extensions.Hosting;

namespace ClickUpClone.Server.Services;

public class DbService
{
    private readonly string _dbPath;
    private readonly object _lock = new();
    private readonly JsonSerializerOptions _jsonOptions;

    public DbService(IHostEnvironment env)
    {
        _dbPath = Path.Combine(env.ContentRootPath, "db.json");
        _jsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = null, // Keeps PascalCase to match our seed db.json
            Converters = { new JsonStringEnumConverter() }
        };
    }

    public WorkspaceData ReadData()
    {
        lock (_lock)
        {
            if (!File.Exists(_dbPath))
            {
                return new WorkspaceData();
            }

            var json = File.ReadAllText(_dbPath);
            return JsonSerializer.Deserialize<WorkspaceData>(json, _jsonOptions) ?? new WorkspaceData();
        }
    }

    public void WriteData(WorkspaceData data)
    {
        lock (_lock)
        {
            var json = JsonSerializer.Serialize(data, _jsonOptions);
            File.WriteAllText(_dbPath, json);
        }
    }
}
