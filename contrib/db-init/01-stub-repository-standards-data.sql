INSERT INTO public.assets (id, name, type, last_updated, data) VALUES
(1, 'asset-alpha', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-alpha", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo alpha", "license":"mit"},
  "access":{"teams_with_admin":["team-alpha"], "teams_with_admin_parents":[], "teams":["team-alpha"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(2, 'asset-bravo', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-bravo", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo bravo", "license":"apache-2.0"},
  "access":{"teams_with_admin":["team-bravo"], "teams_with_admin_parents":[], "teams":["team-bravo"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(3, 'asset-charlie', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-charlie", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo charlie", "license":"gpl-3.0"},
  "access":{"teams_with_admin":["team-charlie"], "teams_with_admin_parents":[], "teams":["team-charlie"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(4, 'asset-delta', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-delta", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo delta", "license":"mit"},
  "access":{"teams_with_admin":["team-delta"], "teams_with_admin_parents":[], "teams":["team-delta"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(5, 'asset-echo', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-echo", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo echo", "license":"mit"},
  "access":{"teams_with_admin":["team-echo"], "teams_with_admin_parents":[], "teams":["team-echo"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }'),
(6, 'asset-foxtrot', 'REPOSITORY', NOW(), '{
  "basic":{"name":"asset-foxtrot", "visibility":"public", "delete_branch_on_merge":null, "default_branch_name":"main", "description":"Sample repo foxtrot", "license":"mit"},
  "access":{"teams_with_admin":["team-foxtrot"], "teams_with_admin_parents":[], "teams":["team-foxtrot"], "teams_parents":[]},
  "security_and_analysis":{"secret_scanning_status":"enabled", "push_protection_status":"enabled", "non_provider_patterns":"enabled"},
  "default_branch_protection":{"allow_force_pushes":false, "enforce_admins":true, "require_code_owner_reviews":true}
  }');

INSERT INTO public.relationships (id, type, assets_id, owners_id) VALUES
(1, 'ADMIN_ACCESS', 1, 6),
(2, 'ADMIN_ACCESS', 1, 8),
(3, 'ADMIN_ACCESS', 3, 3),
(4, 'ADMIN_ACCESS', 4, 4),
(5, 'ADMIN_ACCESS', 5, 5),
(6, 'OTHER', 1, 2),
(7, 'OTHER', 2, 3),
(8, 'OTHER', 3, 4),
(9, 'OTHER', 4, 5),
(10, 'OTHER', 5, 8);
