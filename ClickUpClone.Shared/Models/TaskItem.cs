using System;
using System.Collections.Generic;

namespace ClickUpClone.Shared.Models;

public class TaskItem
{
    public Guid Id { get; set; }
    public Guid ListId { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public TaskCompletionStatus Status { get; set; } = TaskCompletionStatus.ToDo;
    public TaskPriority Priority { get; set; } = TaskPriority.Normal;
    public DateTime? DueDate { get; set; }
    public List<string> Tags { get; set; } = new();
    public Guid? ParentTaskId { get; set; }
    public string? Assignee { get; set; }
    public double? TimeEstimate { get; set; }
    public List<TimeLogEntry> TimeLogs { get; set; } = new();
    public List<string> Attachments { get; set; } = new();
    public List<TaskComment> Comments { get; set; } = new();
}
