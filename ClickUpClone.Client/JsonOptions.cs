using System.Text.Json;
using System.Text.Json.Serialization;

namespace ClickUpClone.Client;

public static class JsonOptions
{
    public static readonly JsonSerializerOptions Default = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = null,
        Converters = { new JsonStringEnumConverter() }
    };
}
