.pragma library

var statuses = ["working", "waiting_input", "idle", "unknown", "disconnected"];
function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function integer(value) { return typeof value === "number" && isFinite(value) && Math.floor(value) === value; }
function optionalString(value) { return value === null || typeof value === "string"; }
function validItem(item) {
    if (!object(item) || typeof item.id !== "string" || !item.id || !optionalString(item.timestamp)) return false;
    if (item.type === "message") return typeof item.text === "string" && ["commentary", "final_answer"].indexOf(item.phase) >= 0;
    if (item.type === "user_reply") return typeof item.text === "string";
    if (item.type === "command") return typeof item.command === "string" && typeof item.output === "string"
        && Array.isArray(item.argv) && item.argv.every(function(v) { return typeof v === "string"; })
        && optionalString(item.cwd) && (item.exit_code === null || integer(item.exit_code))
        && ["completed", "failed"].indexOf(item.status) >= 0;
    if (item.type === "file_change") {
        if (!object(item.changes) || ["completed", "failed"].indexOf(item.status) < 0) return false;
        return Object.keys(item.changes).every(function(path) {
            var change = item.changes[path];
            return object(change) && ["add", "update", "delete"].indexOf(change.type) >= 0
                && ["content", "unified_diff", "move_path"].every(function(k) { return change[k] === undefined || optionalString(change[k]); });
        });
    }
    if (item.type === "question") return typeof item.call_id === "string" && Array.isArray(item.questions)
        && item.questions.every(function(q) {
            return object(q) && integer(q.index) && typeof q.question === "string"
                && optionalString(q.question_id) && Array.isArray(q.options) && q.options.every(function(o) {
                    return typeof o === "string" || (object(o) && typeof o.label === "string" && (o.description === undefined || typeof o.description === "string"));
                });
        });
    return false;
}
function validFrame(frame, thread) {
    if (!object(frame) || frame.schema_version !== 1 || !integer(frame.sequence) || frame.sequence < 1
        || !Array.isArray(frame.chats) || frame.chats.length !== 1) return false;
    var chat = frame.chats[0];
    if (!object(chat) || chat.thread_id !== thread || typeof chat.name !== "string"
        || !integer(chat.source_epoch) || chat.source_epoch < 0 || typeof chat.reset !== "boolean"
        || !integer(chat.pending_questions) || chat.pending_questions < 0 || statuses.indexOf(chat.status) < 0
        || !Array.isArray(chat.items)) return false;
    var ids = {};
    return chat.items.every(function(item) {
        if (!validItem(item) || ids["$" + item.id]) return false;
        ids["$" + item.id] = true; return true;
    });
}
function label(item) {
    if (item.type === "message") return item.phase === "final_answer" ? "Результат" : "Ход работы";
    return {command: "Команда", file_change: "Изменения файлов", question: "Вопрос", user_reply: "Ответ пользователя"}[item.type];
}
function body(item) {
    if (item.type === "message" || item.type === "user_reply") return item.text;
    if (item.type === "command") return "$ " + item.command + "\n\n" + item.output + "\n\nexit " + item.exit_code;
    if (item.type === "file_change") return Object.keys(item.changes).map(function(path) {
        var change = item.changes[path];
        return path + " · " + change.type + (change.move_path ? " → " + change.move_path : "")
            + "\n" + (change.unified_diff !== undefined ? change.unified_diff || "" : change.content || "");
    }).join("\n\n");
    return item.questions.map(function(q) {
        return q.question + (q.options.length ? "\n" + q.options.map(function(o) {
            return typeof o === "string" ? o : o.label + (o.description ? " — " + o.description : "");
        }).join("\n") : "");
    }).join("\n\n");
}
