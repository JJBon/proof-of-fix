#!/bin/bash
# Fetch all PR metadata via GraphQL into JSONL (read-only).
out=$1; kind=${2:-pullRequests}
: > "$out"
cursor=""
while :; do
  if [ "$kind" = pullRequests ]; then
    fields='number createdAt closedAt mergedAt state isDraft additions deletions changedFiles authorAssociation author{login} mergedBy{login} reviews{totalCount} comments{totalCount} title'
  else
    fields='number createdAt closedAt state stateReason authorAssociation author{login} labels(first:10){nodes{name}} assignees{totalCount} comments{totalCount} title'
  fi
  after=""; [ -n "$cursor" ] && after=", after:\"$cursor\""
  q="{repository(owner:\"ItsNotRexed\",name:\"Leonida\"){$kind(first:100$after, orderBy:{field:CREATED_AT,direction:ASC}){pageInfo{hasNextPage endCursor} nodes{$fields}}} rateLimit{remaining cost}}"
  r=$(gh api graphql -f query="$q") || { echo "fail at $cursor" >&2; sleep 5; continue; }
  echo "$r" | jq -c ".data.repository.$kind.nodes[]" >> "$out"
  has=$(echo "$r" | jq -r ".data.repository.$kind.pageInfo.hasNextPage")
  cursor=$(echo "$r" | jq -r ".data.repository.$kind.pageInfo.endCursor")
  [ "$has" = true ] || break
done
echo "$r" | jq -c .data.rateLimit >&2
wc -l "$out" >&2
