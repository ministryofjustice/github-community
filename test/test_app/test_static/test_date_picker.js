const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(
    __dirname,
    "../../../app/static/projects/repository_stats/javascript/date-picker.js"
  ),
  "utf8"
);

function element() {
  return {
    children: [],
    listeners: {},
    parentNode: null,
    hidden: true,
    appendChild(child) {
      if (child.parentNode) {
        child.parentNode.removeChild(child);
      }
      this.children.push(child);
      child.parentNode = this;
      return child;
    },
    insertBefore(child, reference) {
      if (child.parentNode) {
        child.parentNode.removeChild(child);
      }
      const index = this.children.indexOf(reference);
      this.children.splice(index, 0, child);
      child.parentNode = this;
      return child;
    },
    removeChild(child) {
      this.children.splice(this.children.indexOf(child), 1);
      child.parentNode = null;
    },
    addEventListener(type, listener) {
      this.listeners[type] = listener;
    },
    querySelector(selector) {
      return this.selectors[selector] || null;
    }
  };
}

function setup(showPickerSupported) {
  const group = element();
  const input = element();
  input.type = "date";
  input.focus = () => { input.focused = true; };
  input.click = () => { input.clicked = true; };
  if (showPickerSupported) {
    input.showPicker = () => { input.pickerOpened = true; };
  }
  group.appendChild(input);

  const button = element();
  const picker = element();
  picker.selectors = {
    'input[type="date"]': input,
    ".app-date-picker__button": button
  };
  picker.appendChild(group);
  picker.appendChild(button);

  const document = {
    readyState: "complete",
    querySelectorAll: () => [picker],
    createElement: () => element(),
    addEventListener() {}
  };
  vm.runInNewContext(script, { document });
  return { button, input };
}

test("calendar button opens the native picker when showPicker is available", () => {
  const { button, input } = setup(true);
  button.listeners.click();

  assert.equal(button.hidden, false);
  assert.equal(input.focused, true);
  assert.equal(input.pickerOpened, true);
  assert.equal(input.clicked, undefined);
});

test("calendar button falls back to clicking the native date input", () => {
  const { button, input } = setup(false);
  button.listeners.click();

  assert.equal(button.hidden, false);
  assert.equal(input.focused, true);
  assert.equal(input.clicked, true);
});
