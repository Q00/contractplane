# COMPOSITE baseline authorization policy (EXPERIMENTAL).
#
# The OPA/Rego analogue of contractplane's deny-by-default AuthorityGate. Input
# is an effect descriptor {sideEffects, grant}. The default is deny; a local
# side effect is allowed; an external side effect is allowed only when an
# explicit external grant is present. This is the "external side effects require
# explicit pre-dispatch authorization" rule expressed as policy-as-code.
package cp.authz

default allow := false

# Local side effects are permitted without an external grant.
allow if {
	input.sideEffects == "local"
}

# External side effects require an explicit external grant.
allow if {
	input.sideEffects == "external"
	input.grant.external == true
}
