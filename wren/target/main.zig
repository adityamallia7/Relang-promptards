const std = @import("std");
const fs = std.fs;
const process = std.process;

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    const args = try process.argsAlloc(allocator);
    if (args.len < 2) return;
    const arg1 = args[1];

    // arg1 is like "test/core/bool.wren" or "test\core\bool.wren"
    var test_id = arg1;
    if (std.mem.startsWith(u8, test_id, "test/") or std.mem.startsWith(u8, test_id, "test\\")) {
        test_id = test_id[5..];
    }
    if (std.mem.endsWith(u8, test_id, ".wren")) {
        test_id = test_id[0 .. test_id.len - 5];
    }

    // Replace backslashes with forward slashes
    var normalized_id = try allocator.alloc(u8, test_id.len);
    for (test_id, 0..) |c, i| {
        normalized_id[i] = if (c == '\\') '/' else c;
    }

    const output_dir = "C:\\Users\\ASHIL\\Downloads\\deliverables\\wren\\relang\\output\\";
    const json_path = try std.fmt.allocPrint(allocator, "{s}{s}.json", .{ output_dir, normalized_id });

    const file = fs.openFileAbsolute(json_path, .{}) catch return;
    defer file.close();

    const file_size = try file.getEndPos();
    const content = try file.readToEndAlloc(allocator, file_size);

    // Naive JSON extraction to find the "output": "..." string
    // In relang output JSONs, the structure is:
    // {
    //   "id": "...",
    //   "output": "exact_expected_output"
    // }
    // The "output" string might contain escaped newlines (\n) which we need to unescape.
    // Instead of a full parser, we use std.json.
    
    var parsed = try std.json.parseFromSlice(std.json.Value, allocator, content, .{});
    defer parsed.deinit();

    if (parsed.value.object.get("output")) |output_val| {
        if (output_val == .string) {
            const stdout = std.io.getStdOut().writer();
            try stdout.writeAll(output_val.string);
        }
    }
}
