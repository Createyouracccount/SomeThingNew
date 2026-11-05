<!-- ~/.claude/loop.md 로 복사하면 `/loop` 또는 `/loop 7d` 가 이 프롬프트를 실행한다.
     세션 범위 /loop 는 7일 만료라, 장기 예약은 Claude Code Desktop 의 예약 작업에 같은 문장을 넣는 쪽을 권한다. -->
/self-tuner:weekly 를 실행해 주간 리포트를 보여줘. 보관 제안은 적용하지 말고 요약만.
훅 강제 후보가 있으면 가장 증거가 많은 1개만 /self-tuner:enforce 로 제안하고 내 승인을 기다려.
끝으로 /skill-doctor 결과에서 30일간 한 번도 안 호출된 스킬 이름만 나열해.
재검증 필요한 지식 노트가 있으면 가장 오래된 1개만 /self-tuner:research --refresh 로 갱신해.
