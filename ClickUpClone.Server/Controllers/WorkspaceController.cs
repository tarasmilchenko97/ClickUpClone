using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using ClickUpClone.Server.Services;
using ClickUpClone.Shared.Models;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace ClickUpClone.Server.Controllers;

[ApiController]
[Route("api/[controller]")]
public class WorkspaceController : ControllerBase
{
    private readonly DbService _dbService;
    private readonly IWebHostEnvironment _env;

    public WorkspaceController(DbService dbService, IWebHostEnvironment env)
    {
        _dbService = dbService;
        _env = env;
    }

    [HttpGet("tree")]
    [ResponseCache(NoStore = true, Location = ResponseCacheLocation.None)]
    public ActionResult<WorkspaceData> GetTree()
    {
        var data = _dbService.ReadData();
        bool changed = false;

        int maxSeq = 0;
        foreach (var task in data.Tasks)
        {
            if (!string.IsNullOrEmpty(task.TaskSeqId) && task.TaskSeqId.StartsWith("TASK-"))
            {
                if (int.TryParse(task.TaskSeqId.Substring(5), out int val))
                {
                    if (val > maxSeq) maxSeq = val;
                }
            }
        }

        foreach (var task in data.Tasks)
        {
            if (string.IsNullOrEmpty(task.TaskSeqId))
            {
                maxSeq++;
                task.TaskSeqId = $"TASK-{maxSeq}";
                changed = true;
            }
        }

        if (changed)
        {
            _dbService.WriteData(data);
        }

        return Ok(data);
    }

    [HttpPost("nodes")]
    public ActionResult<HierarchyNode> CreateNode([FromBody] HierarchyNode node)
    {
        if (node == null || string.IsNullOrWhiteSpace(node.Name))
        {
            return BadRequest("Вузол повинен мати ім'я.");
        }

        var data = _dbService.ReadData();

        if (node.ParentId.HasValue)
        {
            var parent = data.Nodes.FirstOrDefault(n => n.Id == node.ParentId.Value);
            if (parent == null)
            {
                return BadRequest("Батьківський вузол не знайдено.");
            }
            if (parent.Type == NodeType.List)
            {
                return BadRequest("Не можна створювати елементи всередині Списку.");
            }
            if (node.Type == NodeType.Space)
            {
                return BadRequest("Простір (Space) не може бути вкладеним в інші елементи.");
            }
        }

        node.Id = Guid.NewGuid();
        
        var siblings = data.Nodes.Where(n => n.ParentId == node.ParentId).ToList();
        node.SortOrder = siblings.Any() ? siblings.Max(s => s.SortOrder) + 1 : 1;
        
        data.Nodes.Add(node);
        _dbService.WriteData(data);

        return Ok(node);
    }

    [HttpPost("nodes/{id}/move")]
    public IActionResult MoveNode(Guid id, [FromQuery] Guid? parentId, [FromQuery] Guid? targetNodeId, [FromQuery] bool before)
    {
        var data = _dbService.ReadData();
        var node = data.Nodes.FirstOrDefault(n => n.Id == id);
        if (node == null)
        {
            return NotFound("Вузол не знайдено.");
        }

        if (parentId.HasValue)
        {
            if (parentId.Value == id)
            {
                return BadRequest("Вузол не може бути вкладеним у самого себе.");
            }
            var parent = data.Nodes.FirstOrDefault(n => n.Id == parentId.Value);
            if (parent == null)
            {
                return BadRequest("Батьківський вузол не знайдено.");
            }
            if (parent.Type == NodeType.List)
            {
                return BadRequest("Не можна створювати або переносити елементи всередині Списку.");
            }
            if (node.Type == NodeType.Space)
            {
                return BadRequest("Простір (Space) не може бути вкладеним в інші елементи.");
            }
            var ancestors = new List<Guid>();
            var pId = parentId;
            while (pId.HasValue)
            {
                if (pId.Value == id)
                {
                    return BadRequest("Вузол не може бути вкладеним у своїх нащадків.");
                }
                var pNode = data.Nodes.FirstOrDefault(n => n.Id == pId.Value);
                pId = pNode?.ParentId;
            }
        }

        node.ParentId = parentId;

        var siblings = data.Nodes
            .Where(n => n.ParentId == parentId && n.Id != id)
            .OrderBy(n => n.SortOrder)
            .ThenBy(n => n.Name)
            .ToList();

        if (targetNodeId.HasValue)
        {
            var targetIndex = siblings.FindIndex(s => s.Id == targetNodeId.Value);
            if (targetIndex >= 0)
            {
                if (before)
                {
                    siblings.Insert(targetIndex, node);
                }
                else
                {
                    siblings.Insert(targetIndex + 1, node);
                }
            }
            else
            {
                siblings.Add(node);
            }
        }
        else
        {
            siblings.Add(node);
        }

        for (int i = 0; i < siblings.Count; i++)
        {
            siblings[i].SortOrder = i + 1;
        }

        _dbService.WriteData(data);
        return Ok(node);
    }

    [HttpPut("nodes/{id}")]
    public ActionResult<HierarchyNode> UpdateNode(Guid id, [FromBody] HierarchyNode updatedNode)
    {
        if (updatedNode == null || string.IsNullOrWhiteSpace(updatedNode.Name))
        {
            return BadRequest("Вузол повинен мати ім'я.");
        }

        var data = _dbService.ReadData();
        var node = data.Nodes.FirstOrDefault(n => n.Id == id);
        if (node == null)
        {
            return NotFound("Вузол не знайдено.");
        }

        node.Name = updatedNode.Name;
        node.ParentId = updatedNode.ParentId;
        _dbService.WriteData(data);

        return Ok(node);
    }

    [HttpDelete("nodes/{id}")]
    public IActionResult DeleteNode(Guid id)
    {
        var data = _dbService.ReadData();
        var node = data.Nodes.FirstOrDefault(n => n.Id == id);
        if (node == null)
        {
            return NotFound("Вузол не знайдено.");
        }

        // Delete node and all of its descendants recursively.
        var nodesToDelete = new List<HierarchyNode>();
        GetDescendants(id, data.Nodes, nodesToDelete);
        nodesToDelete.Add(node);

        var nodeIdsToDelete = nodesToDelete.Select(n => n.Id).ToHashSet();

        data.Nodes = data.Nodes.Where(n => !nodeIdsToDelete.Contains(n.Id)).ToList();

        // Delete tasks associated with deleted lists
        var listIdsToDelete = nodesToDelete.Where(n => n.Type == NodeType.List).Select(n => n.Id).ToHashSet();
        data.Tasks = data.Tasks.Where(t => !listIdsToDelete.Contains(t.ListId)).ToList();

        _dbService.WriteData(data);
        return NoContent();
    }

    private void GetDescendants(Guid parentId, List<HierarchyNode> allNodes, List<HierarchyNode> result)
    {
        var children = allNodes.Where(n => n.ParentId == parentId).ToList();
        foreach (var child in children)
        {
            result.Add(child);
            GetDescendants(child.Id, allNodes, result);
        }
    }

    [HttpPost("tasks")]
    public ActionResult<TaskItem> CreateTask([FromBody] TaskItem task)
    {
        if (task == null || string.IsNullOrWhiteSpace(task.Title))
        {
            return BadRequest("Завдання повинно мати заголовок.");
        }

        var data = _dbService.ReadData();

        // Ensure parent list exists
        if (!data.Nodes.Any(n => n.Id == task.ListId && n.Type == NodeType.List))
        {
            return BadRequest("Вказаний список не існує.");
        }

        // Generate TaskSeqId
        int nextId = 1;
        if (data.Tasks.Count > 0)
        {
            var seqNumbers = data.Tasks
                .Select(t => t.TaskSeqId)
                .Where(s => !string.IsNullOrEmpty(s) && s.StartsWith("TASK-"))
                .Select(s => int.TryParse(s.Substring(5), out int val) ? val : 0)
                .ToList();
            if (seqNumbers.Any())
            {
                nextId = seqNumbers.Max() + 1;
            }
        }
        task.TaskSeqId = $"TASK-{nextId}";

        task.Id = Guid.NewGuid();
        data.Tasks.Add(task);
        _dbService.WriteData(data);

        return Ok(task);
    }

    [HttpPut("tasks/{id}")]
    public ActionResult<TaskItem> UpdateTask(Guid id, [FromBody] TaskItem updatedTask)
    {
        if (updatedTask == null || string.IsNullOrWhiteSpace(updatedTask.Title))
        {
            return BadRequest("Завдання повинно мати заголовок.");
        }

        var data = _dbService.ReadData();
        var task = data.Tasks.FirstOrDefault(t => t.Id == id);
        if (task == null)
        {
            return NotFound("Завдання не знайдено.");
        }

        task.Title = updatedTask.Title;
        task.Description = updatedTask.Description;
        task.Status = updatedTask.Status;
        task.Priority = updatedTask.Priority;
        task.DueDate = updatedTask.DueDate;
        task.Tags = updatedTask.Tags ?? new List<string>();
        task.ListId = updatedTask.ListId;
        task.ParentTaskId = updatedTask.ParentTaskId;
        task.Assignee = updatedTask.Assignee;
        task.TimeEstimate = updatedTask.TimeEstimate;
        task.TimeLogs = updatedTask.TimeLogs ?? new List<TimeLogEntry>();
        task.Attachments = updatedTask.Attachments ?? new List<string>();
        task.Comments = updatedTask.Comments ?? new List<TaskComment>();

        _dbService.WriteData(data);
        return Ok(task);
    }

    [HttpPost("tasks/{id}/attachments")]
    public async Task<ActionResult<string>> UploadAttachment(Guid id, [FromForm] IFormFile file)
    {
        if (file == null || file.Length == 0)
        {
            return BadRequest("Файл не обрано або він порожній.");
        }

        var data = _dbService.ReadData();
        var task = data.Tasks.FirstOrDefault(t => t.Id == id);
        if (task == null)
        {
            return NotFound("Завдання не знайдено.");
        }

        var webRoot = _env.WebRootPath ?? Path.Combine(Directory.GetCurrentDirectory(), "wwwroot");
        var uploadsFolder = Path.Combine(webRoot, "uploads");
        if (!Directory.Exists(uploadsFolder))
        {
            Directory.CreateDirectory(uploadsFolder);
        }

        var fileName = $"{Guid.NewGuid()}{Path.GetExtension(file.FileName)}";
        var filePath = Path.Combine(uploadsFolder, fileName);

        using (var stream = new FileStream(filePath, FileMode.Create))
        {
            await file.CopyToAsync(stream);
        }

        var relativePath = $"/uploads/{fileName}";
        task.Attachments.Add(relativePath);
        _dbService.WriteData(data);

        return Ok(new { Path = relativePath });
    }

    [HttpDelete("tasks/{id}")]
    public IActionResult DeleteTask(Guid id)
    {
        var data = _dbService.ReadData();
        var task = data.Tasks.FirstOrDefault(t => t.Id == id);
        if (task == null)
        {
            return NotFound("Завдання не знайдено.");
        }

        var tasksToDelete = new List<TaskItem>();
        GetSubtasksRecursive(id, data.Tasks, tasksToDelete);
        tasksToDelete.Add(task);

        var idsToDelete = tasksToDelete.Select(t => t.Id).ToHashSet();
        data.Tasks = data.Tasks.Where(t => !idsToDelete.Contains(t.Id)).ToList();

        _dbService.WriteData(data);
        return NoContent();
    }

    private void GetSubtasksRecursive(Guid parentTaskId, List<TaskItem> allTasks, List<TaskItem> result)
    {
        var subtasks = allTasks.Where(t => t.ParentTaskId == parentTaskId).ToList();
        foreach (var sub in subtasks)
        {
            result.Add(sub);
            GetSubtasksRecursive(sub.Id, allTasks, result);
        }
    }
}
