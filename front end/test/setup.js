import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// Rete di sicurezza: se jsdom non implementa <dialog>, ChartDialog non potrebbe aprirsi.
const proto = window.HTMLDialogElement.prototype;
if (typeof proto.showModal !== "function") {
  proto.showModal = function () {
    this.setAttribute("open", "");
  };
}
if (typeof proto.close !== "function") {
  proto.close = function () {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
