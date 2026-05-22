using System;

namespace ClickUpClone.Shared.Models;

public class TimeLogEntry
{
    public Guid Id { get; set; }
    public string User { get; set; } = string.Empty;
    public double Hours { get; set; }
    public string Note { get; set; } = string.Empty;
    public DateTime LoggedAt { get; set; }
}
