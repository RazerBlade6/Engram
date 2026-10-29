import { NewPassword } from "@/components/new-password";

/** Invite links land here. */
export default function SetPassword() {
  return (
    <NewPassword
      title="Choose a password"
      expired="Ask for a new invite, or sign in if you already set a password."
    />
  );
}
