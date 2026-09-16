namespace GreenPlan.Web.Tests.Support;

public static class RepositoryPaths
{
    public const string SolutionFileName = "GreenPlan.sln";

    public static DirectoryInfo WebRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var candidate = Path.Combine(directory.FullName, "web", SolutionFileName);
            if (File.Exists(candidate))
            {
                return new DirectoryInfo(Path.Combine(directory.FullName, "web"));
            }

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException($"{SolutionFileName} not found above {AppContext.BaseDirectory}");
    }

    public static IEnumerable<string> SourceFiles(string pattern) =>
        Directory
            .EnumerateFiles(WebRoot().FullName, pattern, SearchOption.AllDirectories)
            .Where(path => !path.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}"))
            .Where(path => !path.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}"))
            .OrderBy(path => path, StringComparer.Ordinal);
}
