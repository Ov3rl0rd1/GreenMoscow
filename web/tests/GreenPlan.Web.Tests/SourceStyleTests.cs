using GreenPlan.Web.Tests.Support;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace GreenPlan.Web.Tests;

public sealed class SourceStyleTests
{
    private static readonly SyntaxKind[] CommentKinds =
    [
        SyntaxKind.SingleLineCommentTrivia,
        SyntaxKind.MultiLineCommentTrivia,
        SyntaxKind.SingleLineDocumentationCommentTrivia,
        SyntaxKind.MultiLineDocumentationCommentTrivia,
    ];

    private static readonly string RazorCommentStart = "@" + "*";
    private static readonly string HtmlCommentStart = "<!" + "--";

    public static TheoryData<string> CSharpFiles() => FilesMatching("*.cs");

    public static TheoryData<string> RazorFiles() => FilesMatching("*.cshtml");

    [Theory]
    [MemberData(nameof(CSharpFiles))]
    public void CSharpSourcesHaveNoComments(string path)
    {
        var lines = CommentLines(File.ReadAllText(path));

        Assert.True(lines.Count == 0, $"{path}: комментарии в строках {string.Join(", ", lines)}");
    }

    [Theory]
    [MemberData(nameof(RazorFiles))]
    public void RazorSourcesHaveNoComments(string path)
    {
        var text = File.ReadAllText(path);

        Assert.DoesNotContain(RazorCommentStart, text);
        Assert.DoesNotContain(HtmlCommentStart, text);
    }

    [Fact]
    public void CommentDetectionFindsAComment()
    {
        var comment = new string('/', 2);

        Assert.NotEmpty(CommentLines($"class Probe {{ }} {comment} note"));
    }

    private static TheoryData<string> FilesMatching(string pattern)
    {
        var data = new TheoryData<string>();
        foreach (var path in RepositoryPaths.SourceFiles(pattern))
        {
            data.Add(path);
        }

        return data;
    }

    private static IReadOnlyList<int> CommentLines(string source) =>
        CSharpSyntaxTree
            .ParseText(source)
            .GetRoot()
            .DescendantTrivia(descendIntoTrivia: true)
            .Where(trivia => CommentKinds.Contains(trivia.Kind()))
            .Select(trivia => trivia.GetLocation().GetLineSpan().StartLinePosition.Line + 1)
            .ToList();
}
