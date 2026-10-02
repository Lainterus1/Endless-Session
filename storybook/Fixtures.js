.pragma library

var dark = {foreground:"#d7ded7",background:"#101819",accent:"#a9d3b5",fontFamily:"monospace"};
var light = {foreground:"#26322d",background:"#f1f3ea",accent:"#356c56",fontFamily:"monospace"};

var stories = [
    {id:"scan",label:"01  Поиск чатов",detail:"0 · начальный обход",count:0,discovery:"scanning"},
    {id:"empty",label:"02  Нет действующих",detail:"0 · обход завершён",count:0,discovery:"ready"},
    {id:"single",label:"03  Один работает",detail:"1 · публичные события",count:1,discovery:"ready"},
    {id:"pair",label:"04  Ожидание ответа",detail:"2 · работа и вопрос",count:2,discovery:"ready"},
    {id:"triple",label:"05  Три секции",detail:"3 · независимые ленты",count:3,discovery:"ready"},
    {id:"quad",label:"06  Четыре секции",detail:"4 · полная страница",count:4,discovery:"ready"},
    {id:"pages",label:"07  Семь чатов",detail:"7 · две страницы",count:7,discovery:"ready"},
    {id:"unknown",label:"08  Источник неизвестен",detail:"1 · неопределённость",count:1,discovery:"unknown"},
    {id:"loss",label:"09  Потеря связи",detail:"1 · последний контекст",count:1,discovery:"unknown"},
    {id:"error",label:"10  Ошибка команды",detail:"1 · красный маркер",count:1,discovery:"ready"},
    {id:"done",label:"11  Завершение",detail:"1 · итоговый блок",count:1,discovery:"ready"},
    {id:"burst",label:"12  Поток событий",detail:"1 · push и дрейф",count:1,discovery:"ready"}
];

function uuid(index) {
    return "00000000-0000-4000-8000-" + String(index + 1).padStart(12, "0");
}
function message(id, text, phase) {
    return {id:id,type:"message",phase:phase || "commentary",timestamp:null,text:text};
}
function command(id, failed) {
    return {id:id,type:"command",timestamp:null,command:"python3 -m unittest",
        argv:["python3","-m","unittest"],cwd:null,
        output:failed ? "Одна проверка упала: не совпал ожидаемый состав чатов." : "Все выбранные проверки прошли.",
        status:failed ? "failed" : "completed",exit_code:failed ? 1 : 0};
}
function change(id) {
    return {id:id,type:"file_change",timestamp:null,status:"completed",
        changes:{"ui/ContextLane.qml":{type:"update",
            unified_diff:"- pushOffset = oldOffset\n+ pushOffset = oldOffset - distance\n+ drift starts after push"}}};
}
function question(id) {
    return {id:id,type:"question",timestamp:null,call_id:"fictional-question",
        questions:[{index:0,question_id:null,question:"Какой вариант показать первым в галерее?",
            options:["Один чат","Несколько чатов"]}]};
}
function initial(story) {
    var chats = [];
    for (var i = 0; i < story.count; i++) {
        var status = "working";
        if (story.id === "pair" && i === 1) status = "waiting_input";
        if (story.id === "triple" && i === 2) status = "idle";
        if (story.id === "quad" && i === 2) status = "waiting_input";
        if (story.id === "pages" && i === 5) status = "waiting_input";
        if (story.id === "loss") status = "disconnected";
        if (story.id === "unknown") status = "unknown";
        if (story.id === "done") status = "idle";
        var items = [message("opening-" + i,
            i % 2 ? "Сверяю состояние интерфейса и доступные публичные события." :
                "Проверяю состав действующих чатов. Служебные сессии не должны занимать отдельную панель.")];
        if (i % 3 === 1) items.push(command("command-" + i, false));
        if (i % 3 === 2) items.push(change("change-" + i));
        if (story.id === "error") items.push(command("error-" + i, true));
        if (status === "waiting_input") items.push(question("question-" + i));
        if (status === "idle") items.push(message("final-" + i,
            "Готово. Публичный результат сохранён в ленте.", "final_answer"));
        chats.push({thread_id:uuid(i),name:[
            "Плагин заставки","Проверка источника","Оформление карточек","Тема Omarchy",
            "Многоколоночный экран","Вопрос пользователя","Финальная сверка"][i],
            source_epoch:0,status:status,pending_questions:status === "waiting_input" ? 1 : 0,
            reset:true,items:items});
    }
    return chats;
}
var longText = "Сверяю длинный публичный фрагмент после изменения размера экрана. " +
    "Карточка должна целиком сохранять текст, переносить строки по ширине своей секции и не перекрывать соседние блоки. " +
    "Визуальная проверка показывает реальное поведение компонента QML, а не подготовленную картинку. " +
    "При появлении следующего события вся очередь быстро сдвигается вверх, после чего продолжает плавное движение.";
var steps = [
    {caption:"Новый комментарий",item:message("stream-1","Появилось новое публичное событие; очередь сдвигается вверх.")},
    {caption:"Обновление того же ID",item:message("stream-1","Уточнил событие: повторный ID заменяет блок без второго экземпляра.")},
    {caption:"Длинный текст",item:message("stream-2",longText)},
    {caption:"Завершённая команда",item:command("stream-3",false)},
    {caption:"Ошибка команды",item:command("stream-4",true)},
    {caption:"Изменение файла",item:change("stream-5")},
    {caption:"Вопрос",item:question("stream-6")},
    {caption:"Ещё один блок",item:message("stream-7","Новый блок вытолкнул прежние выше.")},
    {caption:"Итог",item:message("stream-8","Проверка завершена; это вымышленный публичный результат.","final_answer")}
];
