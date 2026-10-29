import Link from "next/link";

import { NewPassword } from "@/components/new-password";

/** Password-reset links land here. */
export default function ResetPassword() {
  return (
    <NewPassword
      title="Choose a new password"
      expired={
        <>
          Reset links work once, for an hour.{" "}
          <Link href="/sign-in/forgot" className="font-semibold text-accent underline-offset-4 hover:underline">
            Send a new one
          </Link>
        </>
      }
    />
  );
}
