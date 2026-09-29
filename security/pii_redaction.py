"""
PII Redaction — strips personally identifiable information before
messages reach the LLM, and restores them in responses.

Flow:
  1. User sends: "My SSN is 123-45-6789 and email is alice@test.com"
  2. redact() → "My SSN is [REDACTED_SSN_1] and email is [REDACTED_EMAIL_2]"
  3. Redacted message goes to LLM (LLM never sees real PII)
  4. LLM responds with redacted placeholders
  5. restore() → puts original values back for the user

Mappings are persisted to PostgreSQL (pii_redaction_map table)
so they survive server restarts mid-session.

Production note:
  This uses regex for the demo. In production, replace with:
  - AWS Comprehend (detect PII entities)
  - Microsoft Presidio (NLP-based detection with confidence scores)
  Both give better coverage and fewer false positives.
"""
import re
import logging
from db.repositories.session_repo import session_repo

logger = logging.getLogger("pii_redaction")

# Regex patterns for common PII types
PII_PATTERNS = {
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "CREDIT_CARD": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "PHONE": r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
}


class PIIRedactor:

    async def redact(self, text: str, session_id: str) -> str:
        """
        Scan text for PII, replace with placeholders, persist mappings to DB.

        Returns the redacted text. The LLM sees this version.
        """
        # Load existing mappings so we reuse placeholders for values
        # we've already seen in this session
        existing = await session_repo.get_pii_mappings(session_id)
        reverse_map = {v: k for k, v in existing.items()}

        redacted = text
        counter = len(existing)

        for pii_type, pattern in PII_PATTERNS.items():
            for match in re.finditer(pattern, redacted):
                original = match.group()

                # Reuse existing placeholder if we've seen this value before
                if original in reverse_map:
                    placeholder = reverse_map[original]
                else:
                    counter += 1
                    placeholder = f"[REDACTED_{pii_type}_{counter}]"

                    # Persist to database
                    await session_repo.store_pii_mapping(
                        session_id, placeholder, original, pii_type
                    )
                    reverse_map[original] = placeholder

                redacted = redacted.replace(original, placeholder)
                logger.info(
                    f"[PII] Redacted {pii_type} in session {session_id}"
                )

        return redacted

    async def restore(self, text: str, session_id: str) -> str:
        """
        Replace placeholders with original values from DB.

        Only the final response shown to the user gets restored.
        The conversation history stored in DB keeps the redacted version.
        """
        mappings = await session_repo.get_pii_mappings(session_id)
        restored = text
        for placeholder, original in mappings.items():
            restored = restored.replace(placeholder, original)
        return restored


# Singleton
pii_redactor = PIIRedactor()