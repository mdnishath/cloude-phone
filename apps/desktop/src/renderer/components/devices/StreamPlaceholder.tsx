import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export const StreamPlaceholder = (): JSX.Element => (
  <Card>
    <CardHeader>
      <CardTitle>Live screen</CardTitle>
      <CardDescription>Coming in P1d. For now, use scrcpy on your machine via the command above.</CardDescription>
    </CardHeader>
    <CardContent>
      <Button disabled>Open screen</Button>
    </CardContent>
  </Card>
);
