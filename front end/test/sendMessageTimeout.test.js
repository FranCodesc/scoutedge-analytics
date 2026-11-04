import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, sendMessage } from "../src/api/chatApi";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

/** fetch che non risponde mai: si interrompe solo quando il segnale viene annullato. */
function silentFetch() {
  const fn = vi.fn(
    (_url, { signal }) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("sendMessage: timeout del client", () => {
  it("non interrompe prima di 130 s e a 130 s dà CLIENT_TIMEOUT", async () => {
    silentFetch();
    let result;
    const promise = sendMessage({ message: "ciao" }).catch((err) => {
      result = err;
    });

    // Il back end interrompe a 120 s: a 129,999 s il client deve ancora aspettare.
    await vi.advanceTimersByTimeAsync(129_999);
    expect(result).toBeUndefined();

    await vi.advanceTimersByTimeAsync(1);
    await promise;
    expect(result).toBeInstanceOf(ApiError);
    expect(result.code).toBe("CLIENT_TIMEOUT");
    expect(result.status).toBeNull();
    expect(result.message).toMatch(/troppo tempo/);
  });

  it("a 120 s, quando risponde il server con 504, l'errore è quello del server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((resolve) => {
            setTimeout(
              () =>
                resolve(
                  new Response(
                    JSON.stringify({
                      error: {
                        code: "TIMEOUT",
                        message: "L'elaborazione ha richiesto troppo tempo.",
                      },
                    }),
                    { status: 504 },
                  ),
                ),
              120_000,
            );
          }),
      ),
    );
    let result;
    const promise = sendMessage({ message: "ciao" }).catch((err) => {
      result = err;
    });

    await vi.advanceTimersByTimeAsync(120_000);
    await promise;
    expect(result).toMatchObject({ status: 504, code: "TIMEOUT" });
  });

  it("a risposta arrivata il timer è fermato (nessun timeout tardivo)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ reply: "ok" }))),
    );

    await sendMessage({ message: "ciao" });
    expect(vi.getTimerCount()).toBe(0);
  });
});
