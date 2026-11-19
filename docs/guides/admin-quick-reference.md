# MARS-MMS for admins: quick reference

One page, for the training session (W23-5). Button names are the app's own, in **bold**. Admins do everything technicians do as well: see the [technician quick reference](technician-quick-reference.md).

## Your first week

1. **Two-step sign-in is required for admins.** Within 7 days of your first sign-in, set it up on **My profile** with an authenticator app. Write down the ten recovery codes and keep them away from the phone.
2. **Lost the phone?** Another admin opens **Users**, picks you and taps **Reset two-step sign-in**. You set it up again at your next sign-in. If no admin can, IT runs `reset-totp` on the server (docs site, Infrastructure).
3. **Set an offline PIN** only if you attend visits: **My profile**, **Offline PIN**.

## People and organizations

- **Invite user** (on **Users**): staff and clients get an email with a link that works for 7 days. A client's email also links the client guide (`/help/client`).
- **Registrations**: people who signed up themselves. **Link to an organization** (or create it), then **Approve**, or **Deny** with a reason the person receives.
- A client sees only their own organization's stations and requests. Staff names are visible to clients; staff email addresses and phone numbers are not.
- Disabling a user signs them out everywhere at once.

## Requests

- New client requests arrive as Submitted. **Approve** or **Deny** (the reason goes to the client).
- **Assign** technicians, or let them **Claim** from the Queue. The status after Assigned (Scheduled, In progress, Client Review) moves by itself from the visits and reports: it is never set by hand.
- Clients have 30 days to review finished work, with reminders on days 7, 21 and 28; then it closes by itself.

## Reports

- A final visit report cannot change. **Reopen for correction** makes a new version. During Client Review this sends the request back to In progress and the client's 30 days start again when the corrected report is final.
- **Reports** makes summary PDFs and CSVs. **Audit log** shows who did what; **Check integrity** proves nothing in it was altered.

## Stations

- **QR labels and import** prints label sheets (10 per A4 page). Labels printed from staging open staging: print them again from production.
- Replacing a label's code makes the old printed label stop working.
- Stations never change organization.

## Pilot defects

Write down what happened, the time, your role, the phone and app version, and the request or visit reference, and pass it to the developer. Never put client names or station data in a GitHub issue: the repository is public. Critical and high defects are fixed before the go/no-go.
