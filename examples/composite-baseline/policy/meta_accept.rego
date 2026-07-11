# HARDENED composite meta-policy (EXPERIMENTAL).
#
# The reviewer's proposed constraint: "an accept transition requires a preceding
# verification verdict receipt." Input:
#   {"artifact_sha256": "<sha of the artifact under accept>",
#    "receipt": {"verdict": "...", "artifact_sha256": "...", ...}}
#
# Deny by default; allow the accept only when a PASS receipt bound to THIS exact
# artifact is present. This is a genuine, enforceable meta-invariant — as long as
# the receipt handed to this policy actually came from the independent verifier.
# The policy cannot verify that origin; it can only check verdict + binding.
package cp.accept

default allow := false

allow if {
	input.receipt.verdict == "pass"
	input.receipt.artifact_sha256 == input.artifact_sha256
}
