import type { Metadata } from "next";
import Link from "next/link";

import { COMPANY_NAME, LegalPage, SUPPORT_EMAIL, Section } from "@/components/legal/LegalPage";

export const metadata: Metadata = { title: "Privacy policy" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy policy" updated="October 19, 2026">
      <p>
        {COMPANY_NAME} (&ldquo;Navis&rdquo;, &ldquo;we&rdquo;) helps you find your way around any place. This policy
        explains what we collect, why, who we share it with, and the choices you have. We don&apos;t sell your
        personal data, and we don&apos;t show ads or use advertising trackers.
      </p>

      <Section title="What we collect">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>
            <strong>Account details:</strong> your email address and, if you choose, your name and profile picture
            (from Google or Apple when you sign in with them). Passwords are stored only as a salted scrypt hash;
            we can never see them.
          </li>
          <li>
            <strong>What you save in the app:</strong> your profile (home city or area, preferences), saved places
            and events, and checklist progress, so they&apos;re available on all your devices.
          </li>
          <li>
            <strong>Location, only when you allow it:</strong> used on your device to show nearby places,
            directions, local emergency numbers and events. Coordinates are sent with each request to find
            results and are not stored in your account.
          </li>
          <li>
            <strong>Voice, only when you tap the microphone:</strong> the recording is sent for transcription and
            then discarded. We don&apos;t keep audio.
          </li>
          <li>
            <strong>Questions and searches</strong> you type, used to answer them. Saves and dismissals may be used
            to tailor suggestions to you.
          </li>
          <li>
            <strong>Notifications, only if you turn them on in the app:</strong> a device token from Apple or
            Google so we can send safety alerts for your city and reminders for events you saved. You choose which
            kinds in Account &amp; privacy; signing out or deleting your account removes the token.
          </li>
          <li>
            <strong>Technical data:</strong> IP address, device and browser type, and error logs, kept briefly to
            keep the service secure and working (for example, to stop abuse).
          </li>
        </ul>
      </Section>

      <Section title="Services that process data for us">
        <p>To answer a request we send only what that request needs to these providers:</p>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>AI answers and voice transcription: Groq</li>
          <li>Maps, search, places and directions: MapTiler, Geoapify, OpenStreetMap (Nominatim), Foursquare, Transitous</li>
          <li>Events: Ticketmaster, Luma, Devpost, MLH, dev.events</li>
          <li>Weather, air quality, alerts and reference data: Open-Meteo, U.S. National Weather Service, GDACS, USGS, Wikipedia, Wikivoyage, CityBikes</li>
          <li>Sign-in: Google and Apple, only if you choose them</li>
          <li>Notifications: Firebase Cloud Messaging (Android) and Apple Push Notification service (iOS)</li>
          <li>Hosting of our servers and database</li>
        </ul>
        <p>Searches are sent with an approximate or exact point on the map, never with your name or email.</p>
      </Section>

      <Section title="Cookies and local storage">
        <p>
          We use one essential, secure cookie to keep you signed in, and your device&apos;s local storage for
          preferences like dark mode. No analytics or advertising cookies.
        </p>
      </Section>

      <Section title="How long we keep data">
        <p>
          Account data and what you save stay until you delete them or your account. Technical logs are kept for
          up to 30 days. Cached public results (like a city&apos;s weather) expire within days and aren&apos;t tied
          to you.
        </p>
      </Section>

      <Section title="Your choices and rights">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>
            <strong>Download your data</strong> or <strong>delete your account</strong> at any time from{" "}
            <Link href="/account" className="text-indigo-600 hover:underline dark:text-indigo-400">Account &amp; privacy</Link>{" "}
            in the app. Deleting removes your account and everything synced to it immediately.
          </li>
          <li>Turn off location or microphone access in your device settings at any time.</li>
          <li>
            Depending on where you live (for example under GDPR or CCPA), you may have rights to access, correct,
            delete or port your data and to object to processing. Email us to exercise them.
          </li>
        </ul>
      </Section>

      <Section title="Security">
        <p>
          Connections are encrypted (HTTPS), passwords are hashed, sessions are signed and can be ended on every
          device from the app, and access to our systems is restricted.
        </p>
      </Section>

      <Section title="Children">
        <p>Navis isn&apos;t directed at children under 13, and we don&apos;t knowingly collect their data.</p>
      </Section>

      <Section title="Emergencies">
        <p>
          Emergency and helpline numbers are provided for convenience. Always follow local instructions, and in an
          emergency call the local emergency number directly.
        </p>
      </Section>

      <Section title="Changes and contact">
        <p>
          We&apos;ll update this page when our practices change and note the date above. Questions or requests:{" "}
          <a href={`mailto:${SUPPORT_EMAIL}`} className="text-indigo-600 hover:underline dark:text-indigo-400">{SUPPORT_EMAIL}</a>.
        </p>
      </Section>
    </LegalPage>
  );
}
