using System;

namespace ClickUpClone.Shared.Models;

public class TaskComment
{
    public Guid Id { get; set; }
    public Guid TaskId { get; set; }
    public string Author { get; set; } = string.Empty;
    public string Content { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
}
