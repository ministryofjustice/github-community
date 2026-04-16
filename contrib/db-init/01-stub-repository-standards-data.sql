INSERT INTO public.assets (id, name, type, last_updated, data) VALUES
(101, 'asset-alpha', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-alpha", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo alpha", "license":"mit"},
  "access":{"teams_with_admin":["team-alpha"], "teams_with_admin_parents":[], "teams":["team-alpha"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":true, "enforce_admins":true, "require_code_owner_reviews":true, "dismiss_stale_reviews":true, "required_approving_review_count": 1, "required_signatures":true}
  }'),
(102, 'asset-bravo', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-bravo", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo bravo", "license":"mit"},
  "access":{"teams_with_admin":["team-bravo"], "teams_with_admin_parents":[], "teams":["team-bravo"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":true, "enforce_admins":true, "require_code_owner_reviews":true, "dismiss_stale_reviews":true, "required_approving_review_count": 1}
  }'),
(103, 'asset-charlie', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-charlie", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo charlie", "license":"gpl-3.0"},
  "access":{"teams_with_admin":["team-charlie"], "teams_with_admin_parents":[], "teams":["team-charlie"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(104, 'asset-delta', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-delta", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo delta", "license":"apache-2.0"},
  "access":{"teams_with_admin":["team-delta"], "teams_with_admin_parents":[], "teams":["team-delta"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(105, 'asset-echo', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-echo", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo echo", "license":"mit"},
  "access":{"teams_with_admin":["team-echo"], "teams_with_admin_parents":[], "teams":["team-echo"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"disabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(106, 'asset-foxtrot', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-foxtrot", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo foxtrot", "license":"mit"},
  "access":{"teams_with_admin":["team-foxtrot"], "teams_with_admin_parents":[], "teams":["team-foxtrot"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }');

INSERT INTO public.relationships
(id, type, assets_id, owners_id, last_updated)
VALUES
(101, 'ADMIN_ACCESS', 101, 6, NOW()),
(102, 'ADMIN_ACCESS', 101, 8, NOW()),
(103, 'ADMIN_ACCESS', 103, 3, NOW()),
(104, 'ADMIN_ACCESS', 104, 4, NOW()),
(105, 'ADMIN_ACCESS', 105, 5, NOW()),
(106, 'OTHER', 101, 2, NOW()),
(107, 'OTHER', 102, 3, NOW()),
(108, 'OTHER', 103, 4, NOW()),
(109, 'OTHER', 104, 5, NOW()),
(110, 'OTHER', 105, 8, NOW()),
(111, 'ADMIN_ACCESS', 103, 1, NOW());
