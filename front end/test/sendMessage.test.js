import { describe, expect, it, vi } from "vitest";
import { ApiError, sendMessage } from "../src/api/chatApi";

const SESSION = "3f1c2a9e-7b4d-4e8a-9c1f-2d5e6a7b8c9d";
const OK = {
  sessionId: SESSION,
  newSession: false,
  reply: "Per le richieste ad alta priorità: 2 ore lavorative.",
  chartUrl: null,
  toolsUsed: ["search_handbook"],
  sources: [{ section: "7. SLA e procedura di supporto" }],
};
const GENERIC = "Si è verificato un errore imprevisto. Riprova tra un attimo.";

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** Sostituisce fetch con una funzione finta e la restituisce per ispezionarla. */
function mockFetch(impl) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** Esegue sendMessage e restituisce l'errore lanciato. */
const failure = (params = { message: "ciao" }) =>
  sendMessage(params).then(
    () => {
      throw new Error("sendMessage doveva fallire");
    },
    (err) => err,
  );

describe("sendMessage: risposta 200", () => {
  it("restituisce l'oggetto del contratto così com'è", async () => {
    mockFetch(async () => json(OK));
    await expect(sendMessage({ message: "ciao" })).resolves.toEqual(OK);
  });

  it("senza sessionId il corpo contiene solo il messaggio", async () => {
    const fetchMock = mockFetch(async () => json(OK));
    await sendMessage({ message: "ciao", sessionId: null });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/chat");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ message: "ciao" });
  });

  it("con sessionId lo include nel corpo", async () => {
    const fetchMock = mockFetch(async () => json(OK));
    await sendMessage({ message: "ciao", sessionId: SESSION });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ message: "ciao", sessionId: SESSION });
  });
});

describe("sendMessage: errori nel formato del contratto", () => {
  it.each([
    [400, "INVALID_REQUEST", "Il messaggio non può essere vuoto."],
    [
      409,
      "SESSION_BUSY",
      "Una richiesta è già in corso su questa conversazione.",
    ],
    [
      429,
      "RATE_LIMITED",
      "Troppe richieste in poco tempo. Riprova tra qualche minuto.",
    ],
    [504, "TIMEOUT", "L'elaborazione ha richiesto troppo tempo."],
  ])(
    "%i %s: error.message arriva così com'è",
    async (status, code, message) => {
      mockFetch(async () => json({ error: { code, message } }, status));

      const err = await failure();
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ status, code, message });
    },
  );
});

describe("sendMessage: risposte non previste dal contratto", () => {
  it("errore con JSON in un'altra forma: messaggio generico, non il testo del server", async () => {
    mockFetch(async () => json({ error: "dettaglio interno" }, 500));

    const err = await failure();
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 500,
      code: "INTERNAL_ERROR",
      message: GENERIC,
    });
  });

  it("errore con corpo non JSON (pagina HTML di un proxy): messaggio generico", async () => {
    mockFetch(
      async () => new Response("<html>Bad Gateway</html>", { status: 502 }),
    );

    const err = await failure();
    expect(err).toMatchObject({
      status: 502,
      code: "INTERNAL_ERROR",
      message: GENERIC,
    });
  });

  it("200 con corpo non JSON: errore leggibile, non un'eccezione grezza", async () => {
    mockFetch(async () => new Response("non sono json", { status: 200 }));

    const err = await failure();
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "INTERNAL_ERROR", message: GENERIC });
  });

  it("rete giù: NETWORK_ERROR con messaggio in italiano e status null", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });

    const err = await failure();
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBeNull();
    expect(err.code).toBe("NETWORK_ERROR");
    expect(err.message).toMatch(/Impossibile contattare il server/);
    expect(err.message).not.toMatch(/Failed to fetch/);
  });
});
