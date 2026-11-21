# Mạng: một VNet, hai subnet. Database chỉ có địa chỉ riêng trong VNet; Container Apps chạy trong subnet còn lại.

resource "azurerm_virtual_network" "main" {
  name                = "${local.name}-vnet"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = ["10.20.0.0/16"]
  tags                = local.tags
}

# Subnet của Container Apps environment (workload profiles): tối thiểu /27 và phải uỷ quyền cho Microsoft.App/environments.
resource "azurerm_subnet" "apps" {
  name                 = "apps"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.0.0/24"]

  delegation {
    name = "container-apps"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Subnet riêng của PostgreSQL: không tài nguyên loại khác nào được nằm trong subnet đã uỷ quyền này.
resource "azurerm_subnet" "db" {
  name                 = "db"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.1.0/28"]
  # PostgreSQL flexible server tự thêm service endpoint này vào subnet của nó khi được tạo (thấy ở lần plan thứ hai
  # sau apply ngày 2026-11-21). Khai báo ở đây để Terraform không gỡ nó đi.
  service_endpoints = ["Microsoft.Storage"]

  delegation {
    name = "postgresql"

    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Tên của máy chủ PostgreSQL chỉ phân giải được bên trong VNet.
resource "azurerm_private_dns_zone" "db" {
  name                = "${local.name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "db" {
  name                  = "${local.name}-db-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.db.name
  virtual_network_id    = azurerm_virtual_network.main.id
  tags                  = local.tags
}
