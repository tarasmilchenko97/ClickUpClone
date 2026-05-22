using System.Collections.Generic;

namespace ClickUpClone.Shared.Models;

public class WorkspaceData
{
    public List<HierarchyNode> Nodes { get; set; } = new();
    public List<TaskItem> Tasks { get; set; } = new();
}
