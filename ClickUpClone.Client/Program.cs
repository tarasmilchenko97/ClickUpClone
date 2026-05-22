using Microsoft.AspNetCore.Components.Web;
using Microsoft.AspNetCore.Components.WebAssembly.Hosting;
using ClickUpClone.Client;

var builder = WebAssemblyHostBuilder.CreateDefault(args);
builder.RootComponents.Add<App>("#app");
builder.RootComponents.Add<HeadOutlet>("head::after");

// Connect client HttpClient to the server URL (http://localhost:5048/)
builder.Services.AddScoped(sp => new HttpClient { BaseAddress = new Uri("http://localhost:5048/") });
builder.Services.AddScoped<UserService>();

await builder.Build().RunAsync();

