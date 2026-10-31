import { describe, expect, it } from "vitest";
import { accountLabel, pickerShown, startServer, userOn } from "./signin";

const ONE = [{ server: "local", user: null }];
const TWO = [{ server: "local", user: "amy" }, { server: "second:1666", user: null }];

describe("the sign-in picker (spec 2026-10-31 §9)", () => {
  it("shows only when there is a choice: several servers, and none asked for by a review", () => {
    expect(pickerShown(ONE)).toBe(false);
    expect(pickerShown(TWO)).toBe(true);
    expect(pickerShown(TWO, "second:1666")).toBe(false);
  });

  it("starts on the server asked for, else the first one not signed in to, else the first", () => {
    expect(startServer(TWO, "local")).toBe("local");
    expect(startServer(TWO)).toBe("second:1666");
    expect(startServer(TWO, "nowhere:1")).toBe("second:1666");
    expect(startServer([{ server: "local", user: "amy" }])).toBe("local");
    expect(startServer([])).toBeNull();
  });
});

describe("the account menu", () => {
  const logins = [{ server: "local", user: "amy" }, { server: "second:1666", user: "bob" }];

  it("names the first sign-in and counts the others", () => {
    expect(accountLabel(logins)).toBe("amy +1");
    expect(accountLabel(logins.slice(0, 1))).toBe("amy");
    expect(accountLabel([])).toBe("");
  });

  it("finds the session's user on a server", () => {
    expect(userOn(logins, "second:1666")).toBe("bob");
    expect(userOn(logins, "third:1")).toBeNull();
    expect(userOn(logins, undefined)).toBeNull();
  });
});
