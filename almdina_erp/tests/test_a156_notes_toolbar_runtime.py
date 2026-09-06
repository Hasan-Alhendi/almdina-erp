from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UX = ROOT / "public" / "js" / "door_cutting_order" / "notes" / "door_cutting_order_notes_ux.js"
NODE = shutil.which("node")


def run_scenario() -> dict:
    if NODE is None:
        raise RuntimeError("node is required for browser-lifecycle simulation")

    script = r"""
const fs = require('fs');
const vm = require('vm');

class FakeClassList {
    constructor() { this.values = new Set(); }
    add(value) { this.values.add(value); }
    toggle(value, enabled) {
        if (enabled) this.values.add(value); else this.values.delete(value);
    }
}

function makeButton(label) {
    return {
        nodeType: 1,
        isConnected: true,
        textContent: label,
        title: '',
        dataset: {},
        classList: new FakeClassList(),
        attributes: {},
        setAttribute(name, value) { this.attributes[name] = value; },
        remove() { this.isConnected = false; },
    };
}

const formHandlers = {};
const surfaces = new Map();
const documentContext = {
    registerSurface(name, probe) { surfaces.set(name, probe); return true; },
};

const document = {
    addEventListener() {},
};

const frappe = {
    session: { user: 'designer@example.com' },
    ui: { form: { on(doctype, handlers) { formHandlers[doctype] = handlers; } } },
    call() {
        return Promise.resolve({ message: {
            order: 'DCO-TEST',
            counts: { order: 2 },
            important_note_preview: '',
            important_note_comment: '',
        } });
    },
    msgprint() {},
};

const window = {
    frappe,
    AlmdinaDocumentContext: documentContext,
    AlmdinaNotesPanel: { openForOrder() {} },
    cur_frm: null,
};

const context = {
    window,
    document,
    frappe,
    console,
    Promise,
    CustomEvent: function CustomEvent(name, init) { this.type = name; this.detail = init && init.detail; },
    __: value => value,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(__UX_PATH__, 'utf8'), context);

function makeForm(status) {
    const toolbarRoot = {
        querySelector(selector) {
            if (selector !== '.dco-notes-toolbar-button') return null;
            return this.button && this.button.isConnected ? this.button : null;
        },
        button: null,
    };
    const frm = {
        doctype: 'Door Cutting Order',
        doc: {
            doctype: 'Door Cutting Order',
            name: 'DCO-TEST',
            status,
            current_department: status === 'At Drawing' ? 'رسم' : '',
            current_assignee: status === 'At Drawing' ? 'designer@example.com' : '',
            important_note_preview: '',
            important_note_comment: '',
        },
        page: { wrapper: toolbarRoot },
        custom_buttons: {},
        is_new() { return false; },
        add_custom_button(label, handler) {
            const button = makeButton(label);
            button.handler = handler;
            toolbarRoot.button = button;
            this.custom_buttons[label] = [button];
            return [button];
        },
        remove_custom_button(label) {
            const stored = this.custom_buttons[label];
            const node = stored && stored[0];
            if (node) node.isConnected = false;
            delete this.custom_buttons[label];
            if (toolbarRoot.button === node) toolbarRoot.button = null;
        },
    };
    return frm;
}

(async () => {
    const frm = makeForm('Draft');
    window.cur_frm = frm;
    formHandlers['Door Cutting Order'].refresh(frm);
    await Promise.resolve();
    await Promise.resolve();
    const first = frm.page.wrapper.button;

    if (!first || !first.isConnected || !frm.custom_buttons['الملاحظات']) {
        throw new Error('Notes action did not mount with a stable registry key');
    }

    // Reproduce the reported lifecycle: Frappe rebuilds the toolbar while the
    // same saved order advances into Drawing for the designer.
    first.isConnected = false;
    frm.page.wrapper.button = null;
    frm.doc.status = 'At Drawing';
    frm.doc.current_department = 'رسم';
    frm.doc.current_assignee = 'designer@example.com';

    const surface = surfaces.get('collaborative-notes-toolbar');
    if (!surface) throw new Error('Notes toolbar surface was not registered');
    const readyBeforeRecovery = surface.isReady(frm);
    const recovered = surface.recover(frm);
    const second = frm.page.wrapper.button;

    process.stdout.write(JSON.stringify({
        readyBeforeRecovery,
        recovered,
        secondConnected: Boolean(second && second.isConnected),
        secondLabel: second && second.textContent,
        stableRegistryKey: Boolean(frm.custom_buttons['الملاحظات']),
        status: frm.doc.status,
        assignee: frm.doc.current_assignee,
    }));
})().catch(error => {
    console.error(error);
    process.exit(1);
});
""".replace("__UX_PATH__", json.dumps(str(UX)))

    completed = subprocess.run(
        [NODE, "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


@unittest.skipIf(NODE is None, "node is required for browser-lifecycle simulation")
class TestA156NotesToolbarRuntime(unittest.TestCase):
    def test_saved_dco_notes_button_recovers_after_drawing_toolbar_rebuild(self) -> None:
        result = run_scenario()
        self.assertEqual(result["status"], "At Drawing")
        self.assertEqual(result["assignee"], "designer@example.com")
        self.assertIs(result["readyBeforeRecovery"], False)
        self.assertIs(result["recovered"], True)
        self.assertIs(result["secondConnected"], True)
        self.assertTrue(result["secondLabel"].startswith("الملاحظات"))
        self.assertIs(result["stableRegistryKey"], True)


if __name__ == "__main__":
    unittest.main()
