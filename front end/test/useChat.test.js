import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, sendMessage } from "../src/api/chatApi";
import { useChat } from "../src/hooks/useChat";

// Si sostituisce solo sendMessage: ApiError e chartSrc restano quelli veri.
vi.mock("../src/api/chatApi", async (importOriginal) => ({
  ...(await importOriginal()),
  sendMessage: vi.fn(),
}));

beforeEach(() => {
  sendMessage.mockReset();
});

/** Promessa che si risolve o si rifiuta quando decide il test. */
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const reply = (overrides = {}) => ({
  sessionId: "sessione-1",
  newSession: false,
  reply: "risposta",
  chartUrl: null,
  toolsUsed: [],
  sources: [],
  ...overrides,
});

const roles = (result) => result.current.messages.map((m) => m.role);

/** Invia un messaggio e aspetta che la risposta sia stata elaborata. */
async function sendAndWait(result, text) {
  await act(async () => {
    result.current.send(text);
  });
}

describe("useChat: invio", () => {
  it("parte con il solo benvenuto locale e l'input libero", () => {
    const { result } = renderHook(() => useChat());
    expect(roles(result)).toEqual(["assistant"]);
    expect(result.current.busy).toBe(false);
  });

  it("aggiunge il messaggio dell'utente e la risposta", async () => {
    sendMessage.mockResolvedValue(reply({ reply: "ciao a te" }));
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "  ciao  ");

    expect(sendMessage).toHaveBeenCalledWith({
      message: "ciao",
      sessionId: null,
    });
    expect(roles(result)).toEqual(["assistant", "user", "assistant"]);
    expect(result.current.messages[1].text).toBe("ciao");
    expect(result.current.messages[2].text).toBe("ciao a te");
    expect(result.current.busy).toBe(false);
  });

  it("un messaggio vuoto non parte", async () => {
    const { result } = renderHook(() => useChat());
    let started;
    await act(async () => {
      started = result.current.send("   ");
    });
    expect(started).toBe(false);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("un solo invio alla volta: il secondo, nello stesso istante, viene ignorato", async () => {
    const pending = deferred();
    sendMessage.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useChat());

    let first;
    let second;
    await act(async () => {
      first = result.current.send("uno");
      second = result.current.send("due");
    });

    expect(first).toBe(true);
    expect(second).toBe(false);
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(result.current.busy).toBe(true);
    expect(roles(result)).toEqual(["assistant", "user"]);

    await act(async () => {
      pending.resolve(reply());
    });
    expect(result.current.busy).toBe(false);
  });
});

describe("useChat: sessionId", () => {
  it("lo sovrascrive sempre con quello ricevuto", async () => {
    sendMessage
      .mockResolvedValueOnce(reply({ sessionId: "id-1" }))
      .mockResolvedValueOnce(reply({ sessionId: "id-2" }))
      .mockResolvedValueOnce(reply({ sessionId: "id-3" }));
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "a");
    await sendAndWait(result, "b");
    await sendAndWait(result, "c");

    const sent = sendMessage.mock.calls.map(([params]) => params.sessionId);
    expect(sent).toEqual([null, "id-1", "id-2"]);
  });
});

describe("useChat: errori", () => {
  it("il messaggio dell'utente resta visibile e l'errore mostra error.message", async () => {
    const message =
      "Troppe richieste in poco tempo. Riprova tra qualche minuto.";
    sendMessage.mockRejectedValue(
      new ApiError({ status: 429, code: "RATE_LIMITED", message }),
    );
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "ciao");

    expect(roles(result)).toEqual(["assistant", "user", "error"]);
    expect(result.current.messages[1].text).toBe("ciao");
    const error = result.current.messages[2];
    expect(error.text).toBe(message);
    expect(error.retryable).toBe(true);
    expect(result.current.busy).toBe(false);
  });

  it("per una richiesta sbagliata non si offre 'Riprova'", async () => {
    sendMessage.mockRejectedValue(
      new ApiError({
        status: 400,
        code: "INVALID_REQUEST",
        message: "Il messaggio è troppo lungo.",
      }),
    );
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "ciao");

    expect(result.current.messages[2].retryable).toBe(false);
  });

  it("un errore non previsto mostra un messaggio generico, non il testo tecnico", async () => {
    sendMessage.mockRejectedValue(new Error("TypeError interno segreto"));
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "ciao");

    const error = result.current.messages[2];
    expect(error.role).toBe("error");
    expect(error.text).toMatch(/errore imprevisto/);
    expect(error.text).not.toMatch(/segreto/);
  });

  it("dopo un errore il sessionId precedente resta valido", async () => {
    sendMessage
      .mockResolvedValueOnce(reply({ sessionId: "id-1" }))
      .mockRejectedValueOnce(
        new ApiError({ code: "NETWORK_ERROR", message: "Rete giù." }),
      )
      .mockResolvedValueOnce(reply({ sessionId: "id-1" }));
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "a");
    await sendAndWait(result, "b");
    await sendAndWait(result, "c");

    const sent = sendMessage.mock.calls.map(([params]) => params.sessionId);
    expect(sent).toEqual([null, "id-1", "id-1"]);
  });
});

describe("useChat: sessione scaduta", () => {
  it("alla prima risposta, anche con newSession true, non c'è nessun avviso", async () => {
    sendMessage.mockResolvedValue(reply({ newSession: true }));
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "ciao");

    expect(roles(result)).toEqual(["assistant", "user", "assistant"]);
  });

  it("newSession true a conversazione avviata: avviso discreto prima della risposta", async () => {
    sendMessage
      .mockResolvedValueOnce(reply({ sessionId: "id-1", newSession: true }))
      .mockResolvedValueOnce(
        reply({ sessionId: "id-2", newSession: true, reply: "nuova" }),
      );
    const { result } = renderHook(() => useChat());

    await sendAndWait(result, "a");
    await sendAndWait(result, "b");

    expect(roles(result)).toEqual([
      "assistant",
      "user",
      "assistant",
      "user",
      "notice",
      "assistant",
    ]);
    expect(result.current.messages[4].text).toMatch(/scaduta/);
    expect(result.current.messages[5].text).toBe("nuova");

    // Il nuovo id sostituisce il vecchio.
    sendMessage.mockResolvedValueOnce(reply({ sessionId: "id-2" }));
    await sendAndWait(result, "c");
    expect(sendMessage.mock.calls[2][0].sessionId).toBe("id-2");
  });
});

describe("useChat: Nuova chat", () => {
  it("scarta sessionId e messaggi", async () => {
    sendMessage.mockResolvedValue(reply({ sessionId: "id-1" }));
    const { result } = renderHook(() => useChat());
    await sendAndWait(result, "a");
    expect(result.current.messages).toHaveLength(3);

    act(() => {
      result.current.newChat();
    });

    expect(roles(result)).toEqual(["assistant"]);
    await sendAndWait(result, "b");
    expect(sendMessage.mock.calls[1][0].sessionId).toBeNull();
  });

  it("una risposta tardiva viene scartata e non cambia il sessionId", async () => {
    const late = deferred();
    sendMessage.mockReturnValueOnce(late.promise);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.send("vecchia domanda");
    });
    act(() => {
      result.current.newChat();
    });
    await act(async () => {
      late.resolve(reply({ sessionId: "id-vecchio", reply: "tardiva" }));
    });

    expect(roles(result)).toEqual(["assistant"]);
    expect(result.current.busy).toBe(false);

    sendMessage.mockResolvedValueOnce(reply({ sessionId: "id-nuovo" }));
    await sendAndWait(result, "nuova domanda");
    expect(sendMessage.mock.calls[1][0].sessionId).toBeNull();
  });

  it("anche un errore tardivo viene scartato", async () => {
    const late = deferred();
    sendMessage.mockReturnValueOnce(late.promise);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.send("vecchia domanda");
    });
    act(() => {
      result.current.newChat();
    });
    await act(async () => {
      late.reject(new ApiError({ code: "TIMEOUT", message: "Troppo tardi." }));
    });

    expect(roles(result)).toEqual(["assistant"]);
  });

  it("sblocca subito l'input e la risposta tardiva non lo sblocca per la conversazione nuova", async () => {
    const late = deferred();
    const current = deferred();
    sendMessage
      .mockReturnValueOnce(late.promise)
      .mockReturnValueOnce(current.promise);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.send("vecchia");
    });
    expect(result.current.busy).toBe(true);

    act(() => {
      result.current.newChat();
    });
    expect(result.current.busy).toBe(false);

    await act(async () => {
      result.current.send("nuova");
    });
    expect(result.current.busy).toBe(true);

    // Arriva la risposta della conversazione vecchia: l'input resta bloccato.
    await act(async () => {
      late.resolve(reply({ reply: "tardiva" }));
    });
    expect(result.current.busy).toBe(true);
    expect(roles(result)).toEqual(["assistant", "user"]);

    await act(async () => {
      current.resolve(reply({ reply: "attuale" }));
    });
    expect(result.current.busy).toBe(false);
    expect(result.current.messages.at(-1).text).toBe("attuale");
  });
});

describe("useChat: riprova", () => {
  it("rinvia la stessa domanda senza duplicare il messaggio dell'utente", async () => {
    sendMessage
      .mockRejectedValueOnce(
        new ApiError({ code: "NETWORK_ERROR", message: "Rete giù." }),
      )
      .mockResolvedValueOnce(reply({ reply: "ora sì" }));
    const { result } = renderHook(() => useChat());
    await sendAndWait(result, "domanda");

    const errorMessage = result.current.messages.find(
      (m) => m.role === "error",
    );
    await act(async () => {
      result.current.retry(errorMessage);
    });

    expect(sendMessage.mock.calls[1][0].message).toBe("domanda");
    expect(roles(result)).toEqual(["assistant", "user", "assistant"]);
    expect(result.current.messages[2].text).toBe("ora sì");
  });
});
