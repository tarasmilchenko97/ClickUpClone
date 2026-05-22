using System;

namespace ClickUpClone.Shared.Models;

public class HierarchyNode
{
    public Guid Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public NodeType Type { get; set; }
    public Guid? ParentId { get; set; }
    public int SortOrder { get; set; }
}
