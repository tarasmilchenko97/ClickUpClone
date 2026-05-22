# Stage 1: Build the application
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

# Copy csproj files and restore dependencies
COPY ["ClickUpClone.Server/ClickUpClone.Server.csproj", "ClickUpClone.Server/"]
COPY ["ClickUpClone.Client/ClickUpClone.Client.csproj", "ClickUpClone.Client/"]
COPY ["ClickUpClone.Shared/ClickUpClone.Shared.csproj", "ClickUpClone.Shared/"]
RUN dotnet restore "ClickUpClone.Server/ClickUpClone.Server.csproj"
RUN dotnet restore "ClickUpClone.Client/ClickUpClone.Client.csproj"

# Copy the rest of the source code
COPY . .

# Publish both Client and Server projects
RUN dotnet publish "ClickUpClone.Client/ClickUpClone.Client.csproj" -c Release -o /app/client-publish
RUN dotnet publish "ClickUpClone.Server/ClickUpClone.Server.csproj" -c Release -o /app/server-publish

# Stage 2: Runtime image
FROM mcr.microsoft.com/dotnet/aspnet:9.0 AS runtime
WORKDIR /app
# Copy server published files
COPY --from=build /app/server-publish .
# Copy client published wwwroot (static files) to server's wwwroot folder
COPY --from=build /app/client-publish/wwwroot ./wwwroot

# Expose the port (Railway/Render will route to this port)
EXPOSE 8080

# Environment variable to bind ASP.NET Core to the exposed port
ENV ASPNETCORE_URLS=http://+:8080

# Run the server app
ENTRYPOINT ["dotnet", "ClickUpClone.Server.dll"]
