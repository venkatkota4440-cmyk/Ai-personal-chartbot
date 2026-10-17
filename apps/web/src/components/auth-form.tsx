"use client";

import type { User } from "@shared/types";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, useSyncExternalStore, type FormEvent } from "react";

import { Brand } from "@/components/shell/brand";
import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/states";
import { api, ApiError, safeNextPath } from "@/lib/api";
import { browserTimeZone, listTimeZones } from "@/lib/time";

const MIN_PASSWORD_LENGTH = 12;

// The browser timezone does not change while the page is open, so there is nothing to subscribe to.
const subscribeNever = () => () => {};

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const isRegister = mode === "register";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // The server cannot know the browser's timezone; useSyncExternalStore renders "UTC" on the server and
  // switches to the detected zone after hydration without a mismatch warning.
  const detectedTimezone = useSyncExternalStore(subscribeNever, browserTimeZone, () => "UTC");
  const [chosenTimezone, setTimezone] = useState<string | null>(null);
  const timezone = chosenTimezone ?? detectedTimezone;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const timeZones = useMemo(() => (isRegister ? listTimeZones(timezone) : []), [isRegister, timezone]);

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!/^\S+@\S+\.\S+$/.test(email)) errors.email = "Enter a valid email address";
    if (isRegister && password.length < MIN_PASSWORD_LENGTH)
      errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters`;
    if (!password) errors.password = "Enter your password";
    setClientErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!validate()) return;
    setPending(true);
    try {
      await api<User>(isRegister ? "/api/auth/register" : "/api/auth/login", {
        method: "POST",
        body: isRegister ? { email, password, timezone } : { email, password },
      });
      router.replace(next);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "internal_error", "Unexpected error"));
      setPending(false);
    }
  };

  const serverFieldError = (name: string) => error?.fields.find((f) => f.field === name)?.message;

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm animate-appear">
        <Brand />
        <h1 className="mt-8 text-title1 font-semibold tracking-tight">
          {isRegister ? "Create your account" : "Sign in"}
        </h1>
        <p className="mt-1 text-subhead text-label-2">
          {isRegister ? "Set up your personal assistant workspace." : "Welcome back to your personal assistant."}
        </p>

        <form onSubmit={onSubmit} noValidate className="mt-6 flex flex-col gap-4">
          <TextField
            label="Email"
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={clientErrors.email ?? serverFieldError("email")}
          />
          <TextField
            label="Password"
            type="password"
            name="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            required
            minLength={isRegister ? MIN_PASSWORD_LENGTH : undefined}
            hint={isRegister ? `At least ${MIN_PASSWORD_LENGTH} characters. A passphrase works well.` : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={clientErrors.password ?? serverFieldError("password")}
          />
          {isRegister && (
            <SelectField
              label="Timezone"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              options={timeZones.map((z) => ({ value: z, label: z }))}
              error={serverFieldError("timezone")}
            />
          )}

          {error && <Notice tone="error">{error.message}</Notice>}

          <Button type="submit" loading={pending} className="mt-2 w-full">
            {isRegister ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-subhead text-label-2">
          {isRegister ? "Already have an account? " : "New here? "}
          <Link
            href={isRegister ? "/login" : "/register"}
            className="inline-flex min-h-11 items-center font-semibold text-blue underline-offset-4 hover:underline"
          >
            {isRegister ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </div>
    </main>
  );
}
