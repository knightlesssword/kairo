import { redirect } from "next/navigation";

// entry point routes to /chat, which guards via /auth/me and bounces to /login if unauth.
export default function Home() {
  redirect("/chat");
}
