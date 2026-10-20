//! rmcp client interoperability: a standard rmcp client connects to `/mcp`
//! via `StreamableHttpClientTransport`, performs the full request cycle
//! without session state, and discovers the tool registry.

mod common;

use common::RunningServer;
use rmcp::{ServiceExt, transport::StreamableHttpClientTransport};

#[tokio::test]
async fn rmcp_client_lists_tools_over_the_transport() -> Result<(), Box<dyn std::error::Error>> {
    let server = RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")]);

    let transport =
        StreamableHttpClientTransport::from_uri(format!("http://{}/mcp", server.address));
    let client = ().serve(transport).await?;
    let tools = client.list_tools(Default::default()).await?;

    let names: Vec<&str> = tools.tools.iter().map(|tool| tool.name.as_ref()).collect();
    assert!(
        names.contains(&"search"),
        "a standard rmcp client must discover the search tool: {names:?}"
    );
    Ok(())
}
