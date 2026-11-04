import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageContent from "../src/components/MessageContent";

describe("MessageContent: Markdown", () => {
  it("rende grassetto, elenchi e tabelle", () => {
    const text = [
      "Un testo **importante**.",
      "",
      "- uno",
      "- due",
      "",
      "| ruolo | media |",
      "| --- | --- |",
      "| CB | 65.1 |",
    ].join("\n");
    render(<MessageContent text={text} />);

    expect(screen.getByText("importante").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "65.1" })).toBeInTheDocument();
  });

  it("un link valido si apre in una nuova scheda senza accesso alla pagina di origine", () => {
    render(<MessageContent text="[sito](https://example.com/pagina)" />);

    const link = screen.getByRole("link", { name: "sito" });
    expect(link).toHaveAttribute("href", "https://example.com/pagina");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});

describe("MessageContent: nessun HTML grezzo e nessuna immagine", () => {
  it("un <script> non diventa un elemento: resta testo visibile", () => {
    const { container } = render(
      <MessageContent text="Ciao <script>alert(1)</script> fine" />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });

  it("un <img> scritto in HTML non diventa un'immagine e non porta attributi pericolosi", () => {
    const { container } = render(
      <MessageContent text={'Guarda <img src="x" onerror="alert(1)">'} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
  });

  it("un link scritto in HTML non diventa un elemento", () => {
    const { container } = render(
      <MessageContent text={'<a href="javascript:alert(1)">clic</a>'} />,
    );

    expect(container.querySelector("a")).toBeNull();
  });

  it("un'immagine Markdown ![](…) non diventa un <img>", () => {
    const { container } = render(
      <MessageContent text="Prima ![logo](https://evil.test/p.png) dopo" />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("evil.test");
  });

  it("un link javascript: perde l'indirizzo e resta solo il testo", () => {
    const { container } = render(
      <MessageContent text="[clicca](javascript:alert(1))" />,
    );

    expect(container.querySelector("a")).toBeNull();
    expect(container.innerHTML).not.toContain("javascript:");
    expect(container).toHaveTextContent("clicca");
  });
});
