(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const referenceRoot = window.AlmdinaDoorDrawingReference || Object.create(null);
    const v4 = window.AlmdinaDoorDrawingV4;
    const api = root.WorkspaceApi;
    const editorFactory = root.EditorController;
    const referenceFactory = referenceRoot.ReferenceController;
    const persistence = v4.PersistenceAdapter;
    const projection = v4.ManufacturingProjection;
    if (!api || !editorFactory || !referenceFactory || !persistence || !projection) throw new Error("Professional workspace dependencies are incomplete");

    const PROJECTION_MESSAGES = Object.freeze({
        "missing-boundary":"ارسم محيط الدرفة كاملًا قبل الحفظ.","ambiguous-boundary":"يجب أن يحتوي الرسم على محيط واحد فقط.","open-boundary":"أغلق المحيط بالعودة إلى نقطة البداية.","too-few-edges":"محيط الدرفة يحتاج ثلاثة أضلاع على الأقل.","disconnected-boundary":"محيط الدرفة غير متصل بالكامل.","zero-length-edge":"يوجد ضلع بطول صفر.","unclosed-boundary":"محيط الدرفة غير مغلق هندسيًا."
    });
    function confirmAsync(message){return new Promise(resolve=>frappe.confirm(message,()=>resolve(true),()=>resolve(false)));}
    function mount(wrapper) {
        const main = wrapper.querySelector(".layout-main-section");
        if (!main) throw new Error("Drawing page main section is missing");
        let editor = null;
        let context = null;
        let generation = 0;
        let suspended = false;
        let referenceDispose = null;
        const referenceController = referenceFactory.create({ api });

        function destroyEditor(){
            if(referenceDispose){referenceDispose();referenceDispose=null;}
            if(editor){editor.destroy();editor=null;}
        }
        function showLoading(){destroyEditor();main.innerHTML='<div class="ald-prof-fatal" style="color:#777">يتم تحميل مساحة الرسم…</div>';}
        function showRouteError(message){destroyEditor();main.innerHTML=`<div class="ald-prof-fatal">${frappe.utils.escape_html(String(message||"تعذر فتح الرسم."))}</div>`;}
        function backToOrder(){if(context&&context.order&&context.order.name)frappe.set_route("Form","Door Cutting Order",context.order.name);else frappe.set_route("List","Door Cutting Order");}
        function syncReferenceButton(){
            const button=main.querySelector('[data-action="reference-image"]');
            if(!button)return;
            const hasImage=Boolean(context&&context.reference&&context.reference.file_url);
            button.classList.toggle("has-image",hasImage);
            button.textContent=hasImage?"الصورة المرجعية ✓":"صورة مرجعية";
        }
        function bindReferenceButton(){
            const button=main.querySelector('[data-action="reference-image"]');
            if(!button)return;
            const handler=async event=>{
                event.preventDefault();
                event.stopPropagation();
                if(!context||referenceController.isBusy())return;
                const updated=await referenceController.open(context);
                if(updated)context=updated;
                syncReferenceButton();
            };
            button.addEventListener("click",handler);
            referenceDispose=()=>button.removeEventListener("click",handler);
            syncReferenceButton();
        }
        async function save(document){if(!editor||!context||!context.permissions.can_edit)return;const projected=projection.project(document);if(!projected.ok){frappe.msgprint(PROJECTION_MESSAGES[projected.code]||"تعذر تجهيز هندسة تصنيع صالحة من الرسم.");return;}editor.setSaving(true);try{const result=await api.save(context.order.name,context.piece.name,persistence.toStored(document),JSON.stringify(projected.geometry));context={...context,piece:result.piece};editor.markSaved();frappe.show_alert({message:"تم حفظ الرسم وهندسة التصنيع.",indicator:"green"},3);}catch(error){console.error("Professional drawing save failed",error);frappe.msgprint("تعذر حفظ الرسم. تحقق من صلاحيات الطلب وصحة المحيط ثم حاول مرة أخرى.");}finally{if(editor)editor.setSaving(false);}}
        async function requestBack(dirty){if(!dirty){backToOrder();return;}const accepted=await confirmAsync("لديك تعديلات غير محفوظة. هل تريد العودة إلى الطلب دون حفظ؟");if(accepted)backToOrder();}
        async function open(route){
            const token=++generation;suspended=false;showLoading();
            try{
                const [loaded,referenceResult]=await Promise.all([
                    api.load(route.orderName,route.pieceName),
                    api.loadReferenceImage(route.orderName,route.pieceName),
                ]);
                if(token!==generation||suspended)return;
                context={...loaded,reference:referenceResult.reference||{file_url:"",metadata_json:""}};
                const document=persistence.fromStored(loaded.piece.special_shape_drawing_json,loaded.piece);
                main.innerHTML="";
                editor=editorFactory.create({container:main,document,readOnly:!loaded.permissions.can_edit,meta:{orderName:loaded.order.name,pieceLabel:`درفة ${loaded.piece.piece_no||""}`},onSave:save,onBack:requestBack});
                bindReferenceButton();
                if(!loaded.permissions.can_edit&&loaded.permissions.edit_reason)frappe.show_alert({message:loaded.permissions.edit_reason,indicator:"orange"},5);
            }catch(error){console.error("Professional drawing workspace load failed",error);if(token===generation)showRouteError("تعذر تحميل الدرفة. افتح الرسم من الطلب وتحقق من الصلاحيات.");}
        }
        function suspend(){suspended=true;generation+=1;destroyEditor();context=null;}
        return Object.freeze({open,suspend,showRouteError,destroy:suspend});
    }
    root.WorkspaceController = Object.freeze({ mount });
})();
