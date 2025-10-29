## User Story - Business Need

Annual audit of notification logging to satisfy AU-02(e) by confirming key event types remain captured and addressing any gaps.

- [ ] Ticket is understood and QA has been contacted

### User Story

**As** a VA Notify developer meeting NIST/VA AU-02(e),
**I want** an to verify our key logging event types on an annual basis,
**So that** we maintain compliance and situational awareness.

### Additional Info and Resources

- [NIST SP 800-53 Rev. 4 — AU-02(e)](https://csf.tools/reference/nist-sp-800-53/r4/au/au-2/)
- [VA Information Security Policy — AU-02(e) Guidance](https://dvagov.sharepoint.com/sites/oitknowledgeservice/SitePages/Information%20Security%20Policy%20(ISP).aspx)

### Key Event Types to Verify (not an exhaustive list)

- [ ] Creating a user
- [ ] Creating a template
- [ ] Regenerating or expiring an API key
- [ ] Deactivating a service
- [ ] Other high-risk actions identified during the review

## Engineering Checklist

- [ ] Confirm each key event type listed above emits the expected log entry; document follow-up tickets for any gaps.
- [ ] Validate alerting/monitoring dashboards surface AU-02(e) key events and update docs if adjustments are required.
- [ ] Coordinate with QA to exercise new or updated logging in lower environments and capture evidence.

## Acceptance Criteria

- [ ] Logging coverage for AU-02(e) key events is confirmed or remediation work is ticketed.
- [ ] Docs reflect any updates made during the review.
- [ ] Findings, decisions, and next steps are summarized before closing this issue.

## QA Considerations

- [ ] QA validates that key event logging can be triggered in a lower environment.
- [ ] QA confirms any new instrumentation or dashboards behave as expected.
- [ ] QA signs off on the review summary and identified follow-up actions.
