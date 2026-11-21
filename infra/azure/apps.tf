# Tính toán: registry, log, Container Apps environment trong VNet, app api và hai job.

resource "azurerm_container_registry" "main" {
  name                = "${local.name}${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  # Không có tài khoản admin: kéo image bằng managed identity (AcrPull), đẩy image bằng az login hoặc CI.
  admin_enabled = false
  tags          = local.tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.name}-logs"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${local.name}-env"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id   = azurerm_subnet.apps.id

  # Chỉ dùng profile Consumption (tính theo giây, có phần miễn phí hằng tháng); không có profile Dedicated nào.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  tags = local.tags
}

locals {
  registry = azurerm_container_registry.main.login_server

  # Cấu hình chung của các container. Không có secret nào ở đây: mật khẩu DB đi qua secret tham chiếu Key Vault.
  app_env = merge(
    {
      AZURE_STORAGE_ACCOUNT   = azurerm_storage_account.media.name
      AZURE_STORAGE_CONTAINER = azurerm_storage_container.media.name
      SERVICEBUS_NAMESPACE    = azurerm_servicebus_namespace.main.name
      SERVICEBUS_QUEUE        = azurerm_servicebus_queue.jobs.name
      POSTGRES_HOST           = azurerm_postgresql_flexible_server.main.fqdn
      POSTGRES_PORT           = "5432"
      POSTGRES_DB             = azurerm_postgresql_flexible_server_database.main.name
      POSTGRES_USER           = azurerm_postgresql_flexible_server.main.administrator_login
      MAX_UPLOAD_BYTES        = tostring(var.max_upload_bytes)
      AUTH_PROVIDER           = var.auth_provider
    },
    var.auth_provider != "oidc" ? {} : {
      OIDC_ISSUER        = var.oidc_issuer
      OIDC_CLIENT_ID     = var.oidc_client_id
      OIDC_JWKS_URL      = var.oidc_jwks_url
      OIDC_AUTHORIZE_URL = var.oidc_authorize_url
      OIDC_TOKEN_URL     = var.oidc_token_url
      OIDC_LOGOUT_URL    = var.oidc_logout_url
      OIDC_EMAIL_CLAIM   = var.oidc_email_claim
    },
  )

  worker_env = merge(local.app_env, {
    # AZURE_CLIENT_ID cho SDK biết dùng identity nào của container.
    AZURE_CLIENT_ID           = azurerm_user_assigned_identity.worker.client_id
    FFMPEG_THREADS            = "1"
    TRANSCODE_TIMEOUT_SECONDS = tostring(var.transcode_timeout_seconds)
  })
}

# ---------- API ----------

resource "azurerm_container_app" "api" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.api_name
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server   = local.registry
    identity = azurerm_user_assigned_identity.api.id
  }

  secret {
    name                = "postgres-password"
    key_vault_secret_id = azurerm_key_vault_secret.db_password.versionless_id
    identity            = azurerm_user_assigned_identity.api.id
  }

  # Đường vào duy nhất từ Internet: HTTPS; HTTP bị chuyển hướng sang HTTPS.
  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.api_min_replicas
    max_replicas = 1

    container {
      name   = "api"
      image  = "${local.registry}/video-portal-api:${var.image_tag}"
      cpu    = var.api_cpu
      memory = var.api_memory

      dynamic "env" {
        for_each = merge(local.app_env, { AZURE_CLIENT_ID = azurerm_user_assigned_identity.api.client_id })

        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "POSTGRES_PASSWORD"
        secret_name = "postgres-password"
      }

      # /health kiểm tra cả kết nối database.
      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.secret_reader]
}

# ---------- Job chuyển mã: chạy khi có message, mỗi lần chạy một video ----------

resource "azurerm_container_app_job" "transcode" {
  count = var.deploy_apps ? 1 : 0

  name                         = "${local.name}-transcode"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  # Giới hạn của một lần chạy. Không để nền tảng tự thử lại: số lần thử do lease trong database quyết định (tối đa 3).
  replica_timeout_in_seconds = var.transcode_timeout_seconds + 300
  replica_retry_limit        = 0

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.worker.id]
  }

  registry {
    server   = local.registry
    identity = azurerm_user_assigned_identity.worker.id
  }

  secret {
    name                = "postgres-password"
    key_vault_secret_id = azurerm_key_vault_secret.db_password.versionless_id
    identity            = azurerm_user_assigned_identity.worker.id
  }

  event_trigger_config {
    parallelism              = 1
    replica_completion_count = 1

    scale {
      min_executions              = 0
      max_executions              = 1
      polling_interval_in_seconds = 30

      # KEDA đếm message trong queue bằng managed identity của worker, không dùng connection string.
      rules {
        name             = "queue"
        custom_rule_type = "azure-servicebus"
        identity_id      = azurerm_user_assigned_identity.worker.id
        metadata = {
          namespace    = azurerm_servicebus_namespace.main.name
          queueName    = azurerm_servicebus_queue.jobs.name
          messageCount = "1"
        }
      }
    }
  }

  template {
    container {
      name   = "worker"
      image  = "${local.registry}/video-portal-worker:${var.image_tag}"
      cpu    = var.worker_cpu
      memory = var.worker_memory

      dynamic "env" {
        for_each = local.worker_env

        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "POSTGRES_PASSWORD"
        secret_name = "postgres-password"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.secret_reader, azurerm_role_assignment.queue_worker]
}

# ---------- Job bảo trì theo lịch: reconcile, gửi lại outbox còn sót, dọn dẹp ----------

resource "azurerm_container_app_job" "maintenance" {
  count = var.deploy_apps ? 1 : 0

  name                         = "${local.name}-maintenance"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  replica_timeout_in_seconds = 300
  replica_retry_limit        = 0

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.worker.id]
  }

  registry {
    server   = local.registry
    identity = azurerm_user_assigned_identity.worker.id
  }

  secret {
    name                = "postgres-password"
    key_vault_secret_id = azurerm_key_vault_secret.db_password.versionless_id
    identity            = azurerm_user_assigned_identity.worker.id
  }

  schedule_trigger_config {
    cron_expression          = var.maintenance_cron
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      # Cùng image với api (không cần FFmpeg), chỉ khác lệnh. `init-db` cũng chạy bằng job này với lệnh ghi đè (README).
      name    = "maintenance"
      image   = "${local.registry}/video-portal-api:${var.image_tag}"
      command = ["flask", "--app", "app.main", "maintain"]
      cpu     = 0.25
      memory  = "0.5Gi"

      dynamic "env" {
        for_each = local.worker_env

        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "POSTGRES_PASSWORD"
        secret_name = "postgres-password"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.secret_reader]
}
