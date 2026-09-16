FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build

WORKDIR /src

COPY src/GreenPlan.Web/GreenPlan.Web.csproj src/GreenPlan.Web/
RUN dotnet restore src/GreenPlan.Web/GreenPlan.Web.csproj

COPY src/ src/
RUN dotnet publish src/GreenPlan.Web/GreenPlan.Web.csproj \
    --configuration Release \
    --no-restore \
    --output /app/publish


FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS web

ENV ASPNETCORE_HTTP_PORTS=8080 \
    Engine__BaseUrl=http://engine:8000/

WORKDIR /app

COPY --from=build /app/publish .

USER $APP_UID

EXPOSE 8080

ENTRYPOINT ["dotnet", "GreenPlan.Web.dll"]
