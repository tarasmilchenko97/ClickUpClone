# Stage 1: Build the application
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

# Copy csproj files and restore dependencies
COPY ["ClickUpClone.Server/ClickUpClone.Server.csproj", "ClickUpClone.Server/"]
COPY ["ClickUpClone.Client/ClickUpClone.Client.csproj", "ClickUpClone.Client/"]
COPY ["ClickUpClone.Shared/ClickUpClone.Shared.csproj", "ClickUpClone.Shared/"]
RUN dotnet restore "ClickUpClone.Server/ClickUpClone.Server.csproj"

# Copy the rest of the source code
COPY . .

# Publish the Server project (which automatically builds and bundles the Client assets)
RUN dotnet publish "ClickUpClone.Server/ClickUpClone.Server.csproj" -c Release -o /app/publish

# Stage 2: Runtime image
FROM mcr.microsoft.com/dotnet/aspnet:9.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .

# Expose the port (Railway/Render will route to this port)
EXPOSE 8080

# Environment variable to bind ASP.NET Core to the exposed port
ENV ASPNETCORE_URLS=http://+:8080

# Run the server app
ENTRYPOINT ["dotnet", "ClickUpClone.Server.dll"]
