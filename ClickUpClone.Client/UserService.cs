using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.JSInterop;

namespace ClickUpClone.Client;

public class UserProfile
{
    public string Email { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;
    public string AvatarColor { get; set; } = "#8A2BE2";
}

public class UserService
{
    private readonly IJSRuntime _jsRuntime;
    private UserProfile? _currentUser;
    private bool _isInitialized = false;

    public event Action? OnChange;

    public UserService(IJSRuntime jsRuntime)
    {
        _jsRuntime = jsRuntime;
    }

    private static readonly Dictionary<string, (string Password, string Name, string Role, string AvatarColor)> PredefinedUsers = new(StringComparer.OrdinalIgnoreCase)
    {
        { "oleksiy@clickup.com", ("developer", "Олексій", "Developer", "#E0B0FF") },
        { "maria@clickup.com", ("qa", "Марія", "QA", "#FF8C00") },
        { "ivan@clickup.com", ("designer", "Іван", "Designer", "#1E90FF") },
        { "olena@clickup.com", ("pm", "Олена", "Project Manager", "#32CD32") },
        { "admin@clickup.com", ("admin", "Адміністратор", "Admin", "#FF1493") }
    };

    public async Task InitializeAsync()
    {
        if (_isInitialized) return;
        try
        {
            var userJson = await _jsRuntime.InvokeAsync<string?>("localStorage.getItem", "currentUser");
            if (!string.IsNullOrEmpty(userJson))
            {
                _currentUser = JsonSerializer.Deserialize<UserProfile>(userJson);
            }
        }
        catch
        {
            // Fail silent if localStorage is not ready/available
        }
        _isInitialized = true;
    }

    public UserProfile? CurrentUser => _currentUser;

    public bool IsAuthenticated => _currentUser != null;

    public async Task<bool> LoginAsync(string email, string password)
    {
        if (PredefinedUsers.TryGetValue(email, out var details))
        {
            if (details.Password == password)
            {
                _currentUser = new UserProfile
                {
                    Email = email,
                    Name = details.Name,
                    Role = details.Role,
                    AvatarColor = details.AvatarColor
                };
                await _jsRuntime.InvokeVoidAsync("localStorage.setItem", "currentUser", JsonSerializer.Serialize(_currentUser));
                NotifyStateChanged();
                return true;
            }
        }
        return false;
    }

    public async Task LogoutAsync()
    {
        _currentUser = null;
        await _jsRuntime.InvokeVoidAsync("localStorage.removeItem", "currentUser");
        NotifyStateChanged();
    }

    private void NotifyStateChanged() => OnChange?.Invoke();
}
