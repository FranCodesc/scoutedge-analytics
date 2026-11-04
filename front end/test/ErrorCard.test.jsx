import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorCard from "../src/components/ErrorCard";

const MESSAGE = "Troppe richieste in poco tempo. Riprova tra qualche minuto.";

describe("ErrorCard", () => {
  it("mostra error.message così com'è", () => {
    render(<ErrorCard message={MESSAGE} />);

    expect(screen.getByRole("alert")).toHaveTextContent(MESSAGE);
    expect(screen.getByText("Qualcosa è andato storto")).toBeInTheDocument();
  });

  it("variante offline: titolo diverso, stesso messaggio", () => {
    render(<ErrorCard message="Server non raggiungibile." offline />);

    expect(screen.getByText("Nessuna connessione")).toBeInTheDocument();
    expect(screen.getByText("Server non raggiungibile.")).toBeInTheDocument();
  });

  it("senza onRetry non c'è il pulsante Riprova", () => {
    render(<ErrorCard message={MESSAGE} />);

    expect(screen.queryByRole("button", { name: /riprova/i })).toBeNull();
  });

  it("con onRetry il pulsante funziona e si spegne con disabled", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <ErrorCard message={MESSAGE} onRetry={onRetry} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /riprova/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(<ErrorCard message={MESSAGE} onRetry={onRetry} disabled />);
    expect(screen.getByRole("button", { name: /riprova/i })).toBeDisabled();
  });
});
