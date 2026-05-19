import { Col, Row, Typography } from 'antd'

export function WorkspacePage() {
  return (
    <section className="page-section workspace-grid">
      <Typography.Title level={2}>做题工作台</Typography.Title>
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <div className="workspace-pane">
            <h3>题面</h3>
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="workspace-pane">
            <h3>代码</h3>
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="workspace-pane">
            <h3>教练</h3>
          </div>
        </Col>
      </Row>
    </section>
  )
}
