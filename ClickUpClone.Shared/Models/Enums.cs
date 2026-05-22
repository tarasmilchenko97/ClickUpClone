namespace ClickUpClone.Shared.Models;

public enum NodeType
{
    Space,
    Folder,
    List
}

public enum TaskCompletionStatus
{
    ToDo,
    ReadyForDevelopment,
    InProgress,
    InReview,
    ReadyForTesting,
    InTesting,
    Tested,
    Done
}

public enum TaskPriority
{
    Urgent,
    High,
    Normal,
    Low
}
