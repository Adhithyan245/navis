import type { Metadata } from "next";
import Link from "next/link";

import { COMPANY_NAME, LegalPage, SUPPORT_EMAIL, Section } from "@/components/legal/LegalPage";

export const metadata: Metadata = { title: "Disclaimer" };

export default function DisclaimerPage() {
  return (
    <LegalPage title="Disclaimer" updated="October 20, 2026">
      <p>
        Navis is an information tool. It collects publicly available information from the web and from third-party
        services and puts it in one place. Please read this page before relying on anything you see in the app. By
        using Navis you accept it, along with our{" "}
        <Link href="/terms" className="text-indigo-600 hover:underline dark:text-indigo-400">terms of service</Link>.
      </p>

      <Section title="Information comes from the web and other sources">
        <p>
          Almost everything in Navis is gathered from public websites, open data and third-party services. That
          includes maps and places (OpenStreetMap and others), live transit (public feeds published by transit
          operators, collected by open projects such as Transitous), events, weather, air quality, alerts, local
          guides, encyclopedia articles, health services and emergency numbers. {COMPANY_NAME} does not create,
          own, control or check this information, and it may be incomplete, out of date or wrong.
        </p>
        <p>
          Some answers, summaries, tips and plans are written by AI from that information. AI can misunderstand
          things, mix up details or state something false with confidence.
        </p>
      </Section>

      <Section title="No guarantee of accuracy">
        <p>
          We do our best to show useful information, but we make no promise that it is accurate, complete, current
          or available. Opening hours, prices, addresses, phone numbers, routes, schedules, events, rules and
          requirements change all the time. Always check important details with the official source (the business,
          operator, organiser, authority or a professional) before you act on them.
        </p>
      </Section>

      <Section title="Live transit, arrival times and directions">
        <p>
          Vehicle positions, arrival times, delays and departures are estimates based on data feeds published by
          transit operators and the published timetable. They can be late, missing, inaccurate or show vehicles that
          never arrive. Navis is not affiliated with, endorsed by or operated by any transit agency or ticketing app
          (for example the MBTA or Chalo). Follow the operator&apos;s own signs, announcements and apps.
        </p>
        <p>
          Directions and travel times are suggestions only. Use your own judgement, follow traffic laws and road
          signs, and watch where you are going. Don&apos;t use the app in a way that distracts you while driving,
          cycling or walking.
        </p>
      </Section>

      <Section title="Not professional advice and not an emergency service">
        <p>
          Nothing in Navis is medical, mental health, legal, immigration, tax, financial, insurance or safety advice.
          Information about neighbourhoods, safety, health services, visas, money or housing is general and may not
          fit your situation. Talk to a qualified professional before making decisions in these areas.
        </p>
        <p>
          <strong>Navis is not an emergency service.</strong> In an emergency, call the local emergency number
          straight away. Emergency numbers and helplines in the app are listed for convenience; check them with local
          authorities.
        </p>
      </Section>

      <Section title="You are responsible for your decisions">
        <p>
          You use Navis at your own risk. Any decision you make or action you take using information from the app is
          your own responsibility, including where you go, how you travel, what you buy, where you live and what
          services you use. Don&apos;t rely on Navis as your only source for anything that affects your health,
          safety, money, legal status or travel plans.
        </p>
      </Section>

      <Section title="Third-party websites and services">
        <p>
          Navis links to and shows content from websites, apps and services we don&apos;t control. Their content,
          bookings, tickets, prices and policies are their responsibility. A link or listing in Navis is not an
          endorsement or recommendation. Names and logos of transit agencies, venues and other organisations belong
          to their owners and are used only to identify them.
        </p>
      </Section>

      <Section title="Limitation of liability">
        <p>
          To the fullest extent the law allows, Navis is provided &ldquo;as is&rdquo; and &ldquo;as available&rdquo;,
          without warranties of any kind, and {COMPANY_NAME} and the people behind it are not liable for any loss,
          injury, damage, missed connection, cost or other harm that results from using, or relying on, the app or
          the information in it. You agree not to hold {COMPANY_NAME} responsible for, and to indemnify it against,
          claims that arise from your use or misuse of Navis. Nothing here limits rights you have under consumer law
          that cannot be waived.
        </p>
      </Section>

      <Section title="Changes and contact">
        <p>
          We may update this disclaimer; the date at the top shows the latest version. Questions or a correction to
          report:{" "}
          <a href={`mailto:${SUPPORT_EMAIL}`} className="text-indigo-600 hover:underline dark:text-indigo-400">{SUPPORT_EMAIL}</a>.
        </p>
      </Section>
    </LegalPage>
  );
}
