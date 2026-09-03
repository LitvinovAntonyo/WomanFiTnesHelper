# Consistent female exercise media — pilot design

Status: awaiting written-spec review

## Objective

Replace the current mixed-person review candidates with technique cards that show
the same adult woman in the same sports outfit in every start and end phase. The
first deliverable is one non-production pilot for `hack_squat`. The pilot must prove
that identity and outfit can be changed without changing exercise geometry.

## Sources of truth

- The verified real exercise photographs remain the source of truth for pose,
  phase, equipment, camera, framing, and contact points.
- The private six-photo identity pack supplied by the user remains the source of
  truth for facial identity, hair colour, and stable appearance.
- The approved visual contract below remains the source of truth for outfit and
  body styling.
- If identity similarity conflicts with exercise geometry, geometry wins and the
  output is rejected rather than repaired by moving the body.

## Fixed visual contract

Every accepted image must show the same adult woman with:

- facial identity derived from the complete private reference pack;
- a very slim, naturally athletic silhouette;
- natural second-size breast proportions;
- a high, smooth ponytail;
- the same minimal black sports top;
- the same very short, fitted, high-waisted black sports shorts;
- opaque, logo-free fabric;
- no jewellery and no visible tattoos.

Body styling may change the visible surface contour only where this does not move
joints or alter exercise technique. It must not lengthen limbs, change grip width,
move feet, or change the torso, pelvis, knee, elbow, or head angles from the source.

## Privacy and repository boundary

The identity photographs are private inputs. They must be copied to a local,
Git-ignored input directory and must not be committed, added to test fixtures,
written into logs, or embedded in reports. Generated likeness outputs remain in a
local review directory until the user explicitly accepts them. Production assets,
the exercise manifest, and the VPS remain unchanged during the pilot.

## Pilot scope

The pilot uses `hack_squat` because its source pair exposes the full body, machine,
foot placement, and load-bearing contact points. Both phases must be processed as
one identity-consistency job:

1. Load the verified start and end source photographs without altering them.
2. Load all six private identity references as one identity pack.
3. Ask the image editor to preserve the two source compositions and to change only
   the depicted person to the fixed visual contract.
4. Protect the hack-squat machine, background, hands, shoulders against the pads,
   feet on the platform, and all contact boundaries from modification.
5. Keep the generated phase images separate from production assets.
6. Add Russian labels and instructions only after image processing, using the
   deterministic card renderer. AI must not render the text.
7. Produce a review comparison containing the two original phases next to the two
   processed phases at readable resolution.

The available image-editing interface does not expose a guaranteed pixel mask,
ControlNet, or skeleton lock. Therefore this is explicitly a feasibility pilot,
not a claim that geometry is automatically preserved. Verification decides whether
the method is safe enough to scale.

## Verification gates

### Identity and styling

- The start and end phases visibly show the same woman.
- Her face is recognisably derived from the supplied identity pack in both views.
- Hair, outfit cut, outfit colour, skin tone, and body styling agree across phases.
- No jewellery, tattoos, extra logos, or invented accessories appear.

### Exercise geometry

- Phase order remains correct.
- Head direction, shoulders, elbows, hands, spine, torso, pelvis, hips, knees,
  lower legs, feet, and stance width remain aligned with the source photographs.
- Hands, shoulders, back, and feet retain their original machine contact points.
- The machine structure, platform, pads, frame, background, camera perspective,
  crop, and subject scale remain unchanged.
- No extra fingers, merged limbs, broken joints, or impossible contact geometry
  appear.

### Review outcome

The pilot is accepted only after both an original-versus-output geometry inspection
and explicit user approval. A failure in either phase rejects the entire pair. A
rejected output is never copied over an existing card and is never marked
`candidate` or `approved` in the manifest.

## Failure handling

- Identity drift with preserved geometry: retry once with stronger use of the same
  identity pack and no change to the technique source.
- Outfit drift with preserved geometry: retry once with the fixed outfit contract.
- Any changed joint, contact point, machine part, phase, or camera geometry: reject
  immediately; do not use the distorted output as a new source.
- If two controlled attempts still change geometry or identity, stop the AI-edit
  route and report that a local mask/pose/depth pipeline or a dedicated photoshoot
  is required. Do not process the remaining exercises.

## Expansion after pilot approval

Only an approved pilot may unlock the remaining exercise pairs. Expansion must keep
the same private identity pack and visual contract, process one exercise at a time,
and present every pair for human review. Existing mixed-person candidates remain
unapproved and production release stays blocked until all required cards, including
`glute_kickback`, have acceptable technique sources and explicit user approval.

## Non-goals

- No full-frame free generation.
- No changes to the workout plan, exercise descriptions, or rest timers.
- No production manifest approvals.
- No Telegram/VPS deployment.
- No attempt to fabricate the missing `glute_kickback` technique source during this
  pilot.
