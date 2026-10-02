.pragma library
function mix(a,b,t) { return Qt.rgba(a.r*(1-t)+b.r*t,a.g*(1-t)+b.g*t,a.b*(1-t)+b.b*t,1); }
function statusLabel(status) { return {working:"Работает",waiting_input:"Ждёт ответа",idle:"Завершено",unknown:"Состояние неизвестно",disconnected:"Потеря связи"}[status] || "Состояние неизвестно"; }
function kind(item) { return item.type === "message" ? (item.phase === "final_answer" ? "Codex · результат" : "Codex · сообщение") : {command:"exec_command",file_change:"Изменение файла",question:"Codex · вопрос",user_reply:"Ты · ответ"}[item.type] || "Codex"; }
function glyph(item) { return item.type === "message" ? (item.phase === "final_answer" ? "✓" : "◇") : {command:"›_",file_change:"±",question:"?",user_reply:"↳"}[item.type] || "◇"; }
